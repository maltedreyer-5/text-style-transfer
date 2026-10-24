# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Heuristic checks of a result.

Deliberately never blocking: the warnings appear next to the result so that
the user decides. Every check works with the conventions of the text
language (decimal separator, quotation marks, function words).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .catalog import LanguagePack
from .metrics import words
from .models import Conflict, Issue

_SPACES = "\u00a0\u202f' "
_NUMBER = re.compile(rf"\d+(?:(?:[.,]|[{_SPACES}](?=\d{{3}}\b))\d+)*")


def normalise_number(raw: str, pack: LanguagePack) -> str:
    chunks = re.split(rf"([.,{_SPACES}])", raw)
    digits, seps = chunks[0::2], chunks[1::2]
    out = digits[0]
    for i, sep in enumerate(seps):
        nxt = digits[i + 1]
        last = i == len(seps) - 1
        if sep == pack.decimal_separator and last:
            out += "." + nxt
        elif sep in pack.group_separators and len(nxt) == 3:
            out += nxt
        else:
            out += "." + nxt
    return out


def numbers(text: str, pack: LanguagePack) -> set[str]:
    return {normalise_number(m.group(0), pack) for m in _NUMBER.finditer(text or "")}


def quotation_count(text: str, pack: LanguagePack) -> int:
    openings = {q[0] for q in pack.quotes} | {'"'}
    pattern = "[" + re.escape("".join(sorted(openings))) + r"]\s*\w"
    return len(re.findall(pattern, text or ""))


def language_scores(text: str, packs: Iterable[LanguagePack]) -> dict[str, float]:
    tokens = [w.lower() for w in words(text)]
    if not tokens:
        return {}
    return {p.code: sum(t in p.function_words for t in tokens) / len(tokens) for p in packs}


def detect_drift(text: str, expected: LanguagePack, packs: Iterable[LanguagePack]) -> str | None:
    """Code of another language the text seems to be written in, or None."""
    if len(words(text)) < 30:
        return None
    scores = language_scores(text, packs)
    best = max(scores, key=scores.get)
    if best != expected.code and scores[best] >= 0.15 and scores[expected.code] < 0.5 * scores[best]:
        return best
    return None


def check_result(
    source: str,
    output: str,
    target: int,
    pack: LanguagePack,
    packs: Iterable[LanguagePack],
) -> list[Issue]:
    issues: list[Issue] = []
    if not output.strip():
        return [Issue("check_empty_output")]
    in_words, out_words = len(source.split()), len(output.split())
    if in_words >= 30:
        if out_words < target * 0.5:
            issues.append(Issue("check_below_target", {"words": out_words, "target": target}))
        # Exceeding the target is the typical sign that the model added
        # evaluations or concluding sentences of its own.
        if out_words > target * 1.25:
            issues.append(Issue("check_above_target", {"words": out_words, "target": target}))
    missing = sorted(numbers(source, pack) - numbers(output, pack))
    if missing:
        issues.append(Issue("check_numbers_missing", {"numbers": ", ".join(missing[:5])}))
    # Lost quotations are the most serious error in quote-rich texts: a
    # statement attributed to a person turns into a claim of the text itself.
    before, after = quotation_count(source, pack), quotation_count(output, pack)
    if before and after < before:
        issues.append(Issue("check_quotes_lost", {"before": before, "after": after}))
    packs = list(packs)
    drift = detect_drift(output, pack, packs)
    if drift:
        issues.append(Issue("check_language_drift", {"expected": pack.code, "found": drift}))
    return issues


def find_conflicts(values: Mapping[str, int | str], conflicts: Iterable[Conflict]) -> list[Conflict]:
    """Conflicting sliders that are both set in their effective (positive) direction."""
    def effective(sid: str) -> bool:
        v = values.get(sid)
        return isinstance(v, str) or (isinstance(v, int) and v > 0)
    return [c for c in conflicts if effective(c.a) and effective(c.b)]


# --- targets and slider directions ---------------------------------------
# Tolerances are deliberately wide: a few sentences already shift an average,
# and a warning that fires on every run teaches people to ignore warnings.

def check_targets(measured: Mapping[str, float], targets: Mapping[str, float], paragraphs: int) -> list[Issue]:
    """Compare the measured result with the profile's targets."""
    issues = []

    def report(key: str) -> None:
        scale = 100.0 if key.endswith("_share") else 1.0
        issues.append(Issue("check_target", {"metric": key, "target": targets[key] * scale,
                                             "actual": measured[key] * scale}))

    for key, value in targets.items():
        if key not in measured:
            continue
        actual = measured[key]
        if key == "sentence_length_mean" and abs(actual - value) > max(3.0, 0.3 * value):
            report(key)
        elif key == "sentences_per_paragraph" and paragraphs >= 3 and abs(actual - value) > max(1.5, 0.5 * value):
            report(key)
        elif key == "commas_per_sentence" and abs(actual - value) > max(0.5, 0.5 * value):
            report(key)
        elif key in ("question_share", "exclamation_share") and abs(actual - value) > 0.15:
            report(key)
    return issues


# slider id -> indicator whose rate should move in the slider's direction
DIRECTIONAL = {"personal": "personal_rate", "hedging": "hedge_rate", "nominal": "nominal_rate",
               "structured": "list_share", "simple": "word_length_mean"}


def check_directions(source: Mapping[str, float], output: Mapping[str, float],
                     values: Mapping[str, int | str]) -> list[Issue]:
    """Did countable features move the way strong sliders ask for (compared with the source)?"""
    if not source or not output:
        return []
    issues = []
    for sid, key in DIRECTIONAL.items():
        value = values.get(sid)
        if not isinstance(value, int) or abs(value) < 4 or key not in source or key not in output:
            continue
        before, after = source[key], output[key]
        rising = value > 0
        if sid == "simple":                 # simpler means shorter words
            rising = not rising
        if key == "list_share":
            wrong = (after == 0) if rising else (after > before)
        elif key == "word_length_mean":
            wrong = after < before * 0.97 if rising else after > before * 1.03
        else:
            if max(before, after) * output.get("words", 0) / 100 < 2:
                continue                     # too few occurrences to say anything
            wrong = after < before * 0.9 if rising else after > before * 1.1
        if wrong:
            scale = 100.0 if key == "list_share" else 1.0
            issues.append(Issue("check_slider_direction", {"slider": sid, "before": before * scale, "after": after * scale}))
    formal = values.get("formal")
    if isinstance(formal, int) and abs(formal) >= 4 and output.get("words", 0) >= 60:
        if formal > 0 and output.get("familiar_rate", 0) > 0:
            issues.append(Issue("check_formal_familiar", {}))
        elif formal < 0 and output.get("formal_rate", 0) > 0 and output.get("familiar_rate", 0) == 0:
            issues.append(Issue("check_informal_formal", {}))
    return issues


def find_target_conflicts(values: Mapping[str, int | str], targets: Mapping[str, float]) -> list[Issue]:
    """Targets that contradict sliders (both end up in the instructions)."""
    length = targets.get("sentence_length_mean")
    if length is None:
        return []
    issues = []
    simple = values.get("simple")
    if isinstance(simple, int) and simple >= 3 and length > 20:
        issues.append(Issue("target_conflict_simple_long", {"length": length}))
    convoluted = values.get("convoluted")
    if ((isinstance(simple, int) and simple <= -3) or (isinstance(convoluted, int) and convoluted >= 5)) and length < 12:
        issues.append(Issue("target_conflict_complex_short", {"length": length}))
    if values.get("cefr_level") in ("A1", "A2") and length > 15:
        issues.append(Issue("target_conflict_level_long", {"length": length}))
    return issues

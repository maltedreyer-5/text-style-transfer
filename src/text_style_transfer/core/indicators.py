# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Countable indicators for some sliders, per text language.

These are counts, not judgements: personal pronouns, formal and familiar
forms of address, hedging words, nominalisations, list lines, word length
and lexical variety. They are used in two ways:

- as evidence in the analysis prompt, so that the model's slider values for
  these features rest on numbers;
- after a run, to compare the result with the source text in the direction
  a slider asks for (for example: "personal +6" but fewer personal pronouns
  than before).

No absolute thresholds are derived from them. Normal values differ between
languages and text types, and there is no calibrated reference for six
languages; a comparison of source and result needs none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .metrics import words

MIN_WORDS = 40
_MATTR_WINDOW = 50
_LIST_LINE = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+|#{1,6}\s+)")
_SENTENCE_START = re.compile(r"(?:^|[.!?…:]\s+|[\"'»«„“”(\n]\s*)$")


def phrase_pattern(phrases: list[str], case_sensitive: bool = False) -> re.Pattern[str] | None:
    """One regular expression for a list of words and phrases.

    Apostrophes match both ' and ’. Entries that end with an apostrophe
    (French elisions such as j') may be followed directly by a letter.
    """
    if not phrases:
        return None
    full, elided = [], []
    for phrase in sorted(phrases, key=len, reverse=True):
        body = re.escape(phrase).replace("'", "['’]").replace(r"\ ", r"\s+")
        (elided if phrase.endswith("'") else full).append(body)
    parts = []
    if full:
        parts.append(r"(?<![^\W\d_])(?:" + "|".join(full) + r")(?![^\W\d_])")
    if elided:
        parts.append(r"(?<![^\W\d_])(?:" + "|".join(elided) + ")")
    return re.compile("|".join(parts), 0 if case_sensitive else re.IGNORECASE)


@dataclass(frozen=True)
class IndicatorRules:
    personal: re.Pattern[str] | None
    formal: re.Pattern[str] | None
    formal_case_sensitive: bool
    familiar: re.Pattern[str] | None
    hedges: re.Pattern[str] | None
    nominal_suffix: re.Pattern[str]

    @classmethod
    def from_data(cls, data: dict) -> IndicatorRules:
        familiar = phrase_pattern(data.get("familiar_address", []))
        if data.get("familiar_regex"):
            familiar = re.compile(data["familiar_regex"], re.IGNORECASE)
        case = bool(data.get("formal_case_sensitive"))
        return cls(
            personal=phrase_pattern(data.get("personal", [])),
            formal=phrase_pattern(data.get("formal_address", []), case_sensitive=case),
            formal_case_sensitive=case,
            familiar=familiar,
            hedges=phrase_pattern(data.get("hedges", [])),
            nominal_suffix=re.compile(data["nominal_suffix"], re.IGNORECASE),
        )


def _count(pattern: re.Pattern[str] | None, text: str) -> int:
    return len(pattern.findall(text)) if pattern else 0


def _formal_count(rules: IndicatorRules, text: str) -> int:
    if rules.formal is None:
        return 0
    if not rules.formal_case_sensitive:
        return _count(rules.formal, text)
    # Capitalised forms (German "Sie", Italian "Lei", Polish "Pan") count only
    # inside a sentence; at the start of a sentence they are ambiguous.
    return sum(1 for m in rules.formal.finditer(text) if not _SENTENCE_START.search(text[:m.start()]))


def _mattr(tokens: list[str]) -> float:
    lowered = [t.lower() for t in tokens]
    if len(lowered) <= _MATTR_WINDOW:
        return len(set(lowered)) / max(1, len(lowered))
    ratios = [len(set(lowered[i:i + _MATTR_WINDOW])) / _MATTR_WINDOW
              for i in range(len(lowered) - _MATTR_WINDOW + 1)]
    return sum(ratios) / len(ratios)


def measure_indicators(text: str, rules: IndicatorRules) -> dict[str, float]:
    """Rates per 100 words, list share, word length and variety; {} for very short texts."""
    tokens = words(text)
    if len(tokens) < MIN_WORDS:
        return {}
    per100 = 100.0 / len(tokens)
    lines = [line for line in text.splitlines() if line.strip()]
    return {
        "personal_rate": _count(rules.personal, text) * per100,
        "formal_rate": _formal_count(rules, text) * per100,
        "familiar_rate": _count(rules.familiar, text) * per100,
        "hedge_rate": _count(rules.hedges, text) * per100,
        "nominal_rate": sum(1 for t in tokens if len(t) >= 6 and rules.nominal_suffix.search(t)) * per100,
        "list_share": sum(1 for line in lines if _LIST_LINE.match(line)) / max(1, len(lines)),
        "word_length_mean": sum(len(t) for t in tokens) / len(tokens),
        "mattr": _mattr(tokens),
        "words": float(len(tokens)),
    }

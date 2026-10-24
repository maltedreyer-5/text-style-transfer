# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Measured text metrics.

Only features that can be counted robustly with plain Python are measured
here. Judgements such as formality or irony are left to the model and are
reported as estimates; a count that looks precise but is not would be
misleading.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterable, Mapping

MIN_WORDS_FOR_METRICS = 80
MIN_SENTENCES_FOR_METRICS = 5
_MATTR_WINDOW = 50

_WORD = re.compile(r"[^\W\d_]+(?:[’'\-][^\W\d_]+)*", re.UNICODE)
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"'»«”“„)\]]*\s+(?=[\"'»«”“„(\[]?[^\W\d_]|\d)", re.UNICODE)
_QUOTE_CHARS = "\"»«„“”‚‘’"


def _protect(text: str, abbreviations: Iterable[str]) -> str:
    for abbr in sorted(abbreviations, key=len, reverse=True):
        text = text.replace(abbr, abbr.replace(".", "\u2024").replace(" ", "\u00a0"))
    return text


def split_sentences(text: str, abbreviations: Iterable[str] = ()) -> list[str]:
    protected = _protect(" ".join(text.split()), abbreviations)
    parts = _SENTENCE_END.split(protected)
    return [p.replace("\u2024", ".").replace("\u00a0", " ").strip() for p in parts if p.strip()]


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def _mattr(tokens: list[str]) -> float:
    lowered = [t.lower() for t in tokens]
    if len(lowered) <= _MATTR_WINDOW:
        return len(set(lowered)) / max(1, len(lowered))
    ratios = [len(set(lowered[i:i + _MATTR_WINDOW])) / _MATTR_WINDOW
              for i in range(len(lowered) - _MATTR_WINDOW + 1)]
    return sum(ratios) / len(ratios)


def measure(text: str, abbreviations: Iterable[str] = (), min_words: int = MIN_WORDS_FOR_METRICS) -> dict[str, float]:
    """Return metrics, or an empty dict if the text is too short to be meaningful.

    Profiles need about 150 words; checking a result against its targets
    works with fewer, because only averages over a few sentences are compared.
    """
    tokens = words(text)
    if len(tokens) < min_words:
        return {}
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences = split_sentences(text, abbreviations)
    lengths = [len(words(s)) for s in sentences if words(s)]
    if len(lengths) < MIN_SENTENCES_FOR_METRICS:
        return {}
    per_paragraph = [len(split_sentences(p, abbreviations)) for p in paragraphs]
    return {
        "sentence_length_mean": statistics.fmean(lengths),
        "sentence_length_sd": statistics.pstdev(lengths) if len(lengths) > 1 else 0.0,
        "sentences_per_paragraph": statistics.fmean(per_paragraph) if per_paragraph else float(len(lengths)),
        "word_length_mean": statistics.fmean(len(t) for t in tokens),
        "mattr": _mattr(tokens),
        "commas_per_sentence": text.count(",") / len(lengths),
        "question_share": sum(s.rstrip(_QUOTE_CHARS + ")").endswith("?") for s in sentences) / len(sentences),
        "exclamation_share": sum(s.rstrip(_QUOTE_CHARS + ")").endswith("!") for s in sentences) / len(sentences),
        "dialogue_share": sum(any(q in s for q in _QUOTE_CHARS) for s in sentences) / len(sentences),
        "words_measured": float(len(tokens)),
    }


def combine(measurements: list[dict[str, float]]) -> dict[str, float]:
    """Word-weighted mean over several texts."""
    usable = [m for m in measurements if m]
    if not usable:
        return {}
    total = sum(m["words_measured"] for m in usable)
    keys = [k for k in usable[0] if k != "words_measured"]
    combined = {k: sum(m[k] * m["words_measured"] for m in usable) / total for k in keys}
    combined["words_measured"] = total
    return combined


def metrics_to_targets(metrics: Mapping[str, float]) -> list[str]:
    """Turn measurements into concrete, approximate instructions (English)."""
    if not metrics:
        return []
    targets = []
    mean = metrics.get("sentence_length_mean")
    if mean:
        spread = metrics.get("sentence_length_sd", 0.0)
        targets.append(f"Average sentence length about {mean:.0f} words "
                       f"(typical range {max(1, mean - spread):.0f} to {mean + spread:.0f})")
    per_para = metrics.get("sentences_per_paragraph")
    if per_para:
        targets.append(f"About {per_para:.0f} sentences per paragraph")
    commas = metrics.get("commas_per_sentence")
    if commas is not None:
        targets.append(f"About {commas:.1f} commas per sentence")
    for key, text in (("question_share", "questions"), ("exclamation_share", "exclamations"),
                      ("dialogue_share", "sentences containing quoted speech")):
        share = metrics.get(key)
        if share is not None and share >= 0.05:
            targets.append(f"About {share * 100:.0f} % {text}, only where the source text allows it")
    return targets

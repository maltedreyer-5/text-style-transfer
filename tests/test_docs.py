# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""The documentation states figures and defaults; these tests keep them equal to the code."""
import re
from pathlib import Path

import pytest

from text_style_transfer.config import Config
from text_style_transfer.core import indicators, metrics, pipeline, profile_code, profiles, skill
from text_style_transfer.ui.app import TARGET_FIELDS

ROOT = Path(__file__).resolve().parents[1]
DOCS = {p: p.read_text(encoding="utf-8") for p in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]}


def mentioned(phrase: str) -> bool:
    return any(phrase in text for text in DOCS.values())


def test_configuration_table_matches_defaults():
    text = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `TST_([A-Z_]+)` \| ([^|]+) \|", text, re.M)
    source = (ROOT / "src" / "text_style_transfer" / "config.py").read_text(encoding="utf-8")
    read = set(re.findall(r'(?:get|integer|number|boolean|path)\("([A-Z_]+)"', source))
    assert {name for name, _ in rows} == read
    cfg = Config()
    for name, documented in rows:
        documented = documented.strip().strip("`")
        if name == "MAX_UPLOAD":
            actual = f"{cfg.max_upload_bytes // (1024 * 1024)}mb"
        else:
            value = getattr(cfg, name.lower())
            if value in (None, "", {}):
                actual = "empty"
            elif isinstance(value, bool):
                actual = str(value).lower()
            elif isinstance(value, float) and value.is_integer():
                actual = str(int(value))
            else:
                actual = str(value)
        assert documented == actual, name


@pytest.mark.parametrize("phrase, actual, expected", [
    ("34 sliders", None, None),
    ("Twelve known conflicts", None, None),
    ("up to ten reference texts", pipeline.MAX_REFERENCE_TEXTS, 10),
    ("up to five pairs", pipeline.MAX_PAIRS, 5),
    ("up to twelve rules", profiles.MAX_RULES, 12),
    ("up to five sliders with an own instruction", profiles.MAX_CUSTOM_SLIDERS, 5),
    ("at most 2,000 characters", profiles.MAX_DESCRIPTION, 2000),
    ("at most 300 characters each", profiles.MAX_RULE, 300),
    ("at most 24 KB", profile_code.MAX_CODE_CHARS, 24 * 1024),
    ("at most 64 KB", profile_code.MAX_JSON_BYTES, 64 * 1024),
    ("about 80 words and five sentences", (metrics.MIN_WORDS_FOR_METRICS, metrics.MIN_SENTENCES_FOR_METRICS), (80, 5)),
    ("at least 40 words", indicators.MIN_WORDS, 40),
    ("at most 64 characters", skill.NAME_MAX, 64),
    ("at most 1,024 characters", skill.DESCRIPTION_MAX, 1024),
    ("about 5,000 tokens", skill.BODY_TOKENS_RECOMMENDED, 5000),
    ("seven values", len(TARGET_FIELDS), 7),
])
def test_documented_figures(catalog, phrase, actual, expected):
    assert mentioned(phrase), phrase
    if phrase == "34 sliders":
        assert len(catalog.sliders) == 34
    elif phrase == "Twelve known conflicts":
        assert len(catalog.conflicts) == 12
    else:
        assert actual == expected


def test_documented_profile_counts(catalog):
    neutral = sum(p.language is None for p in catalog.profiles.values())
    assert mentioned("31 packaged profiles") and len(catalog.profiles) == 31
    assert mentioned("27 language-neutral profiles") and neutral == 27
    assert mentioned("Four classic profiles") and len(catalog.profiles) - neutral == 4


def test_documented_target_ranges_match_interface():
    text = (ROOT / "docs" / "functional.md").read_text(encoding="utf-8")
    for key, low, high, _step, percent in TARGET_FIELDS:
        if not percent:
            assert re.search(rf"\| {low:g} to {high:g} \|", text), key

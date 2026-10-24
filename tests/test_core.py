# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
import pytest

from text_style_transfer.config import Config, ConfigError
from text_style_transfer.core import prompts
from text_style_transfer.core.checks import check_result, detect_drift, find_conflicts, numbers
from text_style_transfer.core.cleanup import clean_output, strip_reasoning
from text_style_transfer.core.documents import DocumentError, read_text, write_export
from text_style_transfer.core.metrics import measure, split_sentences
from text_style_transfer.core.models import Neutralization, Profile


def test_stylize_prompt_orders_by_strength_and_uses_language_examples(catalog):
    profile = Profile(name="x", sliders={"formal": 3, "funny": 9, "cefr_level": "A2"})
    text = prompts.build_stylize_prompt(profile, catalog.sliders, catalog.languages["fr"], 100)
    assert text.index("CEFR LEVEL: A2") < text.index("FUNNY") < text.index("FORMAL")
    assert "In French: vouvoiement" in text
    assert "Write your entire answer in French" in text
    assert "«…»" in text


def test_negative_pole_uses_opposite_heading(catalog):
    text = prompts.build_stylize_prompt(Profile(name="x", sliders={"formal": -6}), catalog.sliders,
                                        catalog.languages["de"], 50)
    assert "INFORMAL (clear, 6/10)" in text and "Du-Anrede" in text


def test_markdown_only_with_positive_structure(catalog):
    pack = catalog.languages["en"]
    on = prompts.build_stylize_prompt(Profile(name="x", sliders={"structured": 4}), catalog.sliders, pack, 50)
    off = prompts.build_stylize_prompt(Profile(name="x", sliders={"structured": -4}), catalog.sliders, pack, 50)
    assert "(Markdown) where it serves" in on and "without Markdown" in off


def test_target_words_follows_length_slider():
    text = " ".join(["word"] * 100)
    assert prompts.target_words(text, Profile(name="x")) == 100
    assert prompts.target_words(text, Profile(name="x", sliders={"length": 10})) == 200
    assert prompts.target_words(text, Profile(name="x", sliders={"length": -10})) == 40


def test_neutralize_prompt_uses_examples(catalog):
    text = prompts.build_neutralize_prompt(Neutralization(True, "gentle", ("intensifiers",)), catalog.languages["pl"])
    assert "„bardzo”" in text and "Intervene as little as possible" in text


@pytest.mark.parametrize("raw, expected", [
    ("<think>plan</think>Text", "Text"),
    ("plan</think>\nText", "Text"),
    ("<think>never closed", ""),
    ("No tags", "No tags"),
])
def test_strip_reasoning(raw, expected):
    assert strip_reasoning(raw).strip() == expected


def test_cleanup_removes_preamble_fence_and_quotes(catalog):
    de = catalog.languages["de"]
    assert clean_output("Hier ist der umgeschriebene Text:\n\n„Der Text.“", de) == "Der Text."
    assert clean_output("```\nDer Text.\n```", de) == "Der Text."
    assert clean_output("Sicher ist die Lage nicht.", de) == "Sicher ist die Lage nicht."
    assert clean_output("Le texte.\n\nRemarque : j'ai adapté le ton.", catalog.languages["fr"]) == "Le texte."


@pytest.mark.parametrize("lang, text, expected", [
    ("en", "costs 3.5 million and 3,500 more", {"3.5", "3500"}),
    ("de", "kostet 3,5 Millionen und 3.500 mehr", {"3.5", "3500"}),
    ("fr", "coûte 3,5 millions et 3 500 de plus", {"3.5", "3500"}),
])
def test_numbers_follow_language_conventions(catalog, lang, text, expected):
    assert numbers(text, catalog.languages[lang]) == expected


def test_checks_report_missing_numbers_and_quotes(catalog):
    de = catalog.languages["de"]
    source = "Sie sagte: „Wir brauchen 3,5 Millionen.“ " + "Weitere Wörter folgen hier. " * 8
    output = "Sie sagte, man brauche Geld. " + "Weitere Wörter folgen hier. " * 8
    codes = {i.code for i in check_result(source, output, len(source.split()), de, catalog.languages.values())}
    assert {"check_numbers_missing", "check_quotes_lost"} <= codes


def test_language_drift_detected(catalog):
    english = "The committee said that it was not possible to approve the plan, but it would look at it again with the city. " * 3
    assert detect_drift(english, catalog.languages["de"], catalog.languages.values()) == "en"
    assert detect_drift(english, catalog.languages["en"], catalog.languages.values()) is None


def test_conflicts_only_in_effective_direction(catalog):
    assert [c.b for c in find_conflicts({"objective": 5, "emotional": 3}, catalog.conflicts)] == ["emotional"]
    assert find_conflicts({"objective": 5, "emotional": -3}, catalog.conflicts) == []


def test_sentence_split_respects_abbreviations(catalog):
    de = catalog.languages["de"]
    assert len(split_sentences("Das gilt z. B. für Dr. Meier. Danach kam er.", de.abbreviations)) == 2


def test_metrics_need_enough_words():
    assert measure("Zu kurz.") == {}
    m = measure(("Ein Satz mit sechs Wörtern hier. " * 40).strip())
    assert round(m["sentence_length_mean"]) == 6 and m["words_measured"] == 240


def test_documents(tmp_path):
    (tmp_path / "a.txt").write_text("Hallo Welt", encoding="utf-8")
    assert read_text(tmp_path / "a.txt", 100) == "Hallo Welt"
    with pytest.raises(DocumentError):
        read_text(tmp_path / "a.txt", 5)
    (tmp_path / "b.exe").write_bytes(b"x")
    with pytest.raises(DocumentError):
        read_text(tmp_path / "b.exe", 100)
    out = write_export(tmp_path / "s", "docx", "Ergebnis", "Original")
    assert out.exists() and out.suffix == ".docx"
    assert read_text(out, 1000) == "Original\n\nOriginal\n\nResult\n\nErgebnis"


def test_config_validation():
    assert Config.from_env({}).host == "127.0.0.1"
    with pytest.raises(ConfigError):
        Config.from_env({"TST_PORT": "abc"})
    with pytest.raises(ConfigError):
        Config.from_env({"TST_LLM_EXTRA_BODY": "[1]"})
    with pytest.raises(ConfigError):
        Config.from_env({"TST_LLM_BASE_URL": "ftp://x"})
    assert Config.from_env({"TST_LLM_EXTRA_BODY": '{"temperature": 0.3}'}).llm_extra_body == {"temperature": 0.3}

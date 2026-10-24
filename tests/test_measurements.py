# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Countable indicators, targets, direction checks and the calibrated analysis."""
import pytest
from conftest import make_config
from fake_llm import FakeLLM

from text_style_transfer.core import prompts
from text_style_transfer.core.checks import check_directions, check_targets, find_target_conflicts
from text_style_transfer.core.indicators import measure_indicators
from text_style_transfer.core.llm import LLMClient
from text_style_transfer.core.models import Profile
from text_style_transfer.core.pipeline import PATH_DIRECT, Pipeline
from text_style_transfer.core.profiles import profile_from_dict, profile_to_dict

SAMPLES = {
    # language: text, expected counts per repetition (personal, formal, familiar, hedges, nominal).
    # Pronouns attached to verbs (enviarme, inviarmi) are not counted; see docs/design/languages.md.
    "de": ("Ich glaube, wir könnten das vielleicht besprechen. Können Sie mir Ihre Meinung schicken? "
           "Die Durchführung der Prüfung folgt. Du hast recht, dein Vorschlag ist gut.", (5, 2, 2, 2, 3)),
    "en": ("I think we might discuss this. Could you send me your opinion? The implementation follows. "
           "You're right, and we'll see.", (7, 0, 2, 2, 1)),
    "fr": ("Je pense que nous pourrions peut-être en parler. Pourriez-vous m'envoyer votre avis ? "
           "J'ai lu ton message, tu as raison. La réalisation suit.", (8, 2, 2, 3, 1)),
    "es": ("Yo creo que quizás podríamos hablar. ¿Podría usted enviarme su opinión? Tú tienes razón, "
           "tu propuesta es buena. La realización sigue.", (4, 1, 2, 3, 1)),
    "it": ("Io penso che forse potremmo parlarne. Potrebbe inviarmi la Sua opinione? Tu hai ragione, "
           "la tua proposta è buona. La realizzazione segue.", (3, 1, 2, 3, 1)),
    "pl": ("Ja myślę, że może moglibyśmy porozmawiać. Czy mógłby Pan przesłać opinię? Ty masz rację, "
           "twoja propozycja jest dobra. Realizacja następuje.", (3, 1, 2, 3, 1)),
}


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_indicators_count_per_language(catalog, lang):
    text, expected = SAMPLES[lang]
    repeated = " ".join([text] * 4)
    m = measure_indicators(repeated, catalog.languages[lang].indicators)
    per100 = 100.0 / m["words"]
    counts = tuple(round(m[k] / per100 / 4) for k in
                   ("personal_rate", "formal_rate", "familiar_rate", "hedge_rate", "nominal_rate"))
    assert counts == expected


def test_capitalised_formal_address_only_inside_sentences(catalog):
    rules = catalog.languages["de"].indicators
    text = ("Sie kam spät nach Hause. " * 5) + ("Darf ich Sie etwas fragen? " * 5)
    m = measure_indicators(text, rules)
    assert round(m["formal_rate"] * m["words"] / 100) == 5     # sentence-initial "Sie" is ambiguous


def test_targets_are_derived_and_validated(catalog):
    data = {"format": "text-style-profile", "version": 1, "name": "x",
            "metrics": {"sentence_length_mean": 18.0, "words_measured": 400, "personal_rate": 3.0}}
    profile, issues = profile_from_dict(data, catalog.sliders)
    assert profile.targets == {"sentence_length_mean": 18.0} and issues == []
    data["targets"] = {"sentence_length_mean": 500, "question_share": 0.2, "nope": 1}
    profile, issues = profile_from_dict(data, catalog.sliders)
    assert profile.targets == {"sentence_length_mean": 80.0, "question_share": 0.2}
    assert len(issues) == 2
    again, _ = profile_from_dict(profile_to_dict(profile), catalog.sliders)
    assert again.targets == profile.targets


def test_check_targets_tolerances():
    targets = {"sentence_length_mean": 15.0, "question_share": 0.1}
    assert check_targets({"sentence_length_mean": 17.0, "question_share": 0.2}, targets, 1) == []
    issues = check_targets({"sentence_length_mean": 25.0, "question_share": 0.4}, targets, 1)
    assert [(i.code, i.params["metric"]) for i in issues] == [("check_target", "sentence_length_mean"),
                                                             ("check_target", "question_share")]
    assert issues[1].params["target"] == pytest.approx(10.0)    # shares are reported in percent


def test_direction_checks():
    source = {"personal_rate": 5.0, "hedge_rate": 1.0, "list_share": 0.0, "word_length_mean": 5.0, "words": 120}
    worse = {"personal_rate": 2.0, "hedge_rate": 3.0, "list_share": 0.0, "word_length_mean": 5.6, "words": 120}
    codes = {i.params["slider"] for i in check_directions(source, worse, {
        "personal": 6, "hedging": 5, "structured": 5, "simple": 6})}
    assert codes == {"personal", "structured", "simple"}       # hedging moved the right way
    assert check_directions(source, worse, {"personal": 2}) == []   # weak settings are not checked
    familiar = {"familiar_rate": 2.0, "formal_rate": 0.0, "words": 80}
    assert [i.code for i in check_directions({"words": 80}, familiar, {"formal": 7})] == ["check_formal_familiar"]


def test_target_conflicts():
    codes = [i.code for i in find_target_conflicts({"simple": 5, "cefr_level": "A2"}, {"sentence_length_mean": 25})]
    assert codes == ["target_conflict_simple_long", "target_conflict_level_long"]
    assert find_target_conflicts({"convoluted": 6}, {"sentence_length_mean": 9})[0].code == "target_conflict_complex_short"
    assert find_target_conflicts({"simple": 5}, {}) == []


def test_analysis_is_calibrated_with_measurements(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        reference = "Ich denke, wir sollten das vielleicht ändern. Du weißt, was ich meine. " * 25
        profile, _ = pipeline.analyze([reference], "de", "Test", "de")
        system = fake.requests[0]["messages"][0]["content"]
        assert "MEASURED IN THE REFERENCE TEXTS" in system and "personal pronouns" in system
        assert "SCALE:" in system and "very strong" in system
        assert profile.metrics["personal_rate"] > 10 and profile.targets["sentence_length_mean"] > 0
        assert set(profile.targets) <= set(prompts.EVIDENCE_LABELS)


def test_run_reports_measurements(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        text = "Wir haben am Montag beschlossen, den Plan noch einmal gründlich zu prüfen. " * 6
        result = pipeline.run(text, "de", Profile(name="x", sliders={"funny": 3},
                                                  targets={"sentence_length_mean": 30.0}), PATH_DIRECT)
        assert result.measured["source"]["sentence_length_mean"] == pytest.approx(12.0)
        assert "check_target" in [i.code for i in result.issues]


def test_skill_uses_edited_targets(catalog):
    from text_style_transfer.core.skill import build_skill

    profile = Profile(name="x", sliders={"funny": 3}, targets={"sentence_length_mean": 14.0})
    md = build_skill(profile, catalog).files["writing-style-x/SKILL.md"]
    assert "Average sentence length about 14 words" in md and "Set by hand" in md


def test_analysis_values_that_contradict_counts():
    from text_style_transfer.core.pipeline import contradictions

    counts = {"hedge_rate": 0.0, "nominal_rate": 2.0, "list_share": 0.0, "personal_rate": 5.0,
              "formal_rate": 0.0, "familiar_rate": 3.0}
    found = {i.params["slider"] for i in contradictions({"hedging": 6, "nominal": 6, "structured": 2, "formal": 7}, counts)}
    assert found == {"hedging", "formal"}       # zero counts only; weak values are not judged
    assert contradictions({"formal": 7}, {}) == []


def test_short_personal_samples_are_measured():
    from text_style_transfer.core.metrics import measure

    sample = "Ich schreibe kurz. Und direkt. Du kennst das. Warum? Weil es so ist. Das ist gut so. " * 6
    assert measure(sample)["words_measured"] >= 80
    assert measure("Ein einziger sehr langer Satz " + "mit vielen Wörtern " * 40 + ".") == {}   # too few sentences

# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
import pytest
from conftest import make_config
from fake_llm import FakeLLM
from text_style_transfer.core.llm import LLMClient, LLMError
from text_style_transfer.core.models import Profile
from text_style_transfer.core.pipeline import PATH_DIRECT, PATH_NEUTRAL, Pipeline, PipelineError

TEXT = "Der Ausschuss hat am Montag beschlossen, den Plan mit 3,5 Millionen Euro zu fördern. " * 3


@pytest.mark.parametrize("mode, attempts, code", [
    ("status500", 3, "llm_status"),
    ("status400", 1, "llm_bad_request"),
    ("empty", 2, "llm_empty"),
    ("length", 1, "llm_budget_exhausted"),
])
def test_exactly_one_retry_layer(mode, attempts, code):
    with FakeLLM(mode) as fake:
        client = LLMClient(make_config(fake.url))
        with pytest.raises(LLMError) as exc:
            client.chat("s", "u", 50)
        assert exc.value.code == code
        assert len(fake.requests) == attempts


def test_no_sampling_parameters_unless_configured():
    with FakeLLM() as fake:
        LLMClient(make_config(fake.url)).chat("s", "u", 50)
        LLMClient(make_config(fake.url, llm_extra_body='{"temperature": 0.2}')).chat("s", "u", 50)
        assert "temperature" not in fake.requests[0] and fake.requests[1]["temperature"] == 0.2


def test_neutral_path_two_calls_and_reuse(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        profile = Profile(name="x", sliders={"formal": 5})
        result = pipeline.run(TEXT, "de", profile, PATH_NEUTRAL)
        assert len(fake.requests) == 2
        assert result.neutral == TEXT.strip()          # reasoning block removed
        assert result.output == TEXT.strip().upper()
        pipeline.run(TEXT, "de", profile, PATH_NEUTRAL, neutral_override=result.neutral)
        assert len(fake.requests) == 3                  # neutral text reused
        pipeline.run(TEXT, "de", profile, PATH_DIRECT)
        assert len(fake.requests) == 4


def test_only_reasoning_is_reported(catalog):
    with FakeLLM("reasoning") as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        with pytest.raises(PipelineError) as exc:
            pipeline.run(TEXT, "de", Profile(name="x", sliders={"funny": 3}), PATH_DIRECT)
        assert exc.value.code == "output_only_reasoning"
        assert len(fake.requests) == 2                  # one retry with hint


def test_input_limits(catalog):
    pipeline = Pipeline(make_config("http://127.0.0.1:9/v1"), catalog, None)
    for text, code in (("", "input_empty"), ("kurz", "input_too_short"), ("x" * 40000, "input_too_long")):
        with pytest.raises(PipelineError) as exc:
            pipeline.check_input(text)
        assert exc.value.code == code


def test_analysis_builds_validated_profile_with_metrics(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        reference = ("Das ist ein Satz mit einigen Wörtern darin. " * 30)
        profile, issues = pipeline.analyze([reference], "de", "Test", "de")
        assert profile.sliders == {"formal": 7, "funny": 4, "cefr_level": "B2"}
        assert profile.language == "de" and profile.origin == "analysis"
        assert [i.code for i in issues] == ["unknown_slider"]
        assert profile.metrics["words_measured"] == 240
        assert "in German" in fake.requests[0]["messages"][0]["content"]


def test_refine_returns_rules(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        assert pipeline.refine([("Es wurde gemacht.", "Wir machten es.")], "de", "en") == ["Prefer active verbs."]
        with pytest.raises(PipelineError):
            pipeline.refine([("gleich", "gleich")], "de", "en")


ENGLISH = "The committee said that it was not possible to approve the plan, but it would look at it again with the city. " * 3


def test_style_needed_on_direct_path(catalog):
    pipeline = Pipeline(make_config("http://127.0.0.1:9/v1"), catalog, None)
    with pytest.raises(PipelineError) as exc:
        pipeline.run(TEXT, "de", Profile(name="x"), PATH_DIRECT)
    assert exc.value.code == "no_style"


def test_neutralisation_only_and_skipped_neutralisation(catalog):
    from text_style_transfer.core.models import Neutralization

    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        result = pipeline.run(TEXT, "de", Profile(name="x"), PATH_NEUTRAL)
        assert len(fake.requests) == 1 and result.output == result.neutral
        assert "neutral_only" in [i.code for i in result.issues]
        styled = Profile(name="x", sliders={"funny": 3}, neutralization=Neutralization(True, "normal", ()))
        result = pipeline.run(TEXT, "de", styled, PATH_NEUTRAL)
        assert len(fake.requests) == 2 and result.path == PATH_DIRECT
        assert "neutral_skipped" in [i.code for i in result.issues]


def test_wrong_text_language_is_reported(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        result = pipeline.run(ENGLISH, "de", Profile(name="x", sliders={"funny": 3}), PATH_DIRECT)
        issue = next(i for i in result.issues if i.code == "input_language_mismatch")
        assert issue.params == {"expected": "de", "found": "en"}


def test_several_short_references_are_measured_together(catalog):
    with FakeLLM() as fake:
        pipeline = Pipeline(make_config(fake.url), catalog, LLMClient(make_config(fake.url)))
        short = "Das ist ein kurzer Satz mit einigen Wörtern. " * 12   # 96 words each
        profile, issues = pipeline.analyze([short, short], "de", "x", "de")
        assert profile.metrics["words_measured"] == 192
        assert "metrics_too_short" not in [i.code for i in issues]

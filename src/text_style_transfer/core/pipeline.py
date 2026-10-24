# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Orchestration of the two transformation paths and of profile creation.

Path "neutral": the text is first neutralised (its own style removed) and
then given the target style. The intermediate text can be edited by the
user and is reused as long as text and neutralisation settings are
unchanged, so trying several target styles costs one neutralisation only.

Path "direct": the target style is applied to the text as it is.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from ..config import Config
from . import prompts
from .catalog import Catalog
from .checks import check_directions, check_result, check_targets, detect_drift, find_target_conflicts
from .cleanup import clean_output, looks_like_meta
from .indicators import measure_indicators
from .llm import LLMClient, LLMError, Reply
from .metrics import MIN_WORDS_FOR_METRICS, combine, measure
from .models import Issue, Neutralization, Profile, has_style
from .profiles import MAX_RULE, TARGET_RANGES, ProfileError, profile_from_dict
from .tokens import estimate_tokens, output_budget

PATH_NEUTRAL = "neutral"
PATH_DIRECT = "direct"
MAX_REFERENCE_TEXTS = 10
MAX_PAIRS = 5
_JSON_BUDGET = 2000


class PipelineError(RuntimeError):
    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass
class Step:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    seconds: float = 0.0


@dataclass
class RunResult:
    source: str
    language: str
    path: str
    output: str
    neutral: str | None
    neutral_key: str | None
    target_words: int
    issues: list[Issue] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    measured: dict[str, dict[str, float]] = field(default_factory=dict)   # "source" / "output"


def contradictions(values: dict, measured: dict) -> list[Issue]:
    """Slider values from the analysis that contradict an unambiguous count.

    Only zero counts are used: "no hedging word at all" is unambiguous,
    "few hedging words" depends on the text type.
    """
    if not measured:
        return []
    issues = []
    zero_if_positive = {"hedging": "hedge_rate", "nominal": "nominal_rate", "structured": "list_share",
                        "personal": "personal_rate"}
    for sid, key in zero_if_positive.items():
        value = values.get(sid)
        if isinstance(value, int) and value >= 4 and measured.get(key, 1) == 0:
            issues.append(Issue("analysis_contradicts_count", {"slider": sid}))
    formal = values.get("formal")
    if isinstance(formal, int) and formal >= 4 and measured.get("formal_rate", 0) == 0 and measured.get("familiar_rate", 0) > 0:
        issues.append(Issue("analysis_contradicts_count", {"slider": "formal"}))
    if isinstance(formal, int) and formal <= -4 and measured.get("familiar_rate", 0) == 0 and measured.get("formal_rate", 0) > 0:
        issues.append(Issue("analysis_contradicts_count", {"slider": "formal"}))
    return issues


def neutral_cache_key(text: str, language: str, settings: Neutralization) -> str:
    raw = f"{language}\n{settings.key()}\n{text}".encode()
    return hashlib.sha256(raw).hexdigest()


class Pipeline:
    def __init__(self, config: Config, catalog: Catalog, llm: LLMClient) -> None:
        self.config = config
        self.catalog = catalog
        self.llm = llm

    # -- helpers -------------------------------------------------------------

    def _pack(self, language: str):
        pack = self.catalog.languages.get(language)
        if pack is None:
            raise PipelineError("unknown_language", language=language)
        return pack

    def check_input(self, text: str) -> None:
        tokens = estimate_tokens(text)
        if not text.strip():
            raise PipelineError("input_empty")
        if tokens < self.config.min_input_tokens:
            raise PipelineError("input_too_short", minimum=self.config.min_input_tokens)
        if tokens > self.config.max_input_tokens:
            raise PipelineError("input_too_long", tokens=tokens, limit=self.config.max_input_tokens)

    def _budget(self, words: int) -> int:
        c = self.config
        return output_budget(words, c.output_token_factor, c.output_token_min, c.output_token_max)

    def _rewrite(self, system: str, text: str, budget: int, pack) -> Step:
        started = time.monotonic()
        reply: Reply = self.llm.chat(system, text, budget)
        cleaned = clean_output(reply.text, pack)
        prompt_t, completion_t = reply.prompt_tokens, reply.completion_tokens
        if not cleaned or looks_like_meta(cleaned, pack):
            # One retry with an explicit hint; a second failure is reported.
            reply = self.llm.chat(system + "\n\n" + prompts.META_RETRY_HINT, text, budget)
            cleaned = clean_output(reply.text, pack)
            prompt_t = (prompt_t or 0) + (reply.prompt_tokens or 0)
            completion_t = (completion_t or 0) + (reply.completion_tokens or 0)
            if not cleaned:
                raise PipelineError("output_only_reasoning")
        return Step(cleaned, prompt_t, completion_t, time.monotonic() - started)

    # -- transformation ------------------------------------------------------

    def neutralize(self, text: str, language: str, settings: Neutralization) -> Step:
        pack = self._pack(language)
        system = prompts.build_neutralize_prompt(settings, pack)
        budget = self._budget(len(text.split()))
        return self._rewrite(system, text, budget, pack)

    def stylize(self, text: str, source: str, language: str, profile: Profile) -> tuple[Step, int]:
        pack = self._pack(language)
        words = prompts.target_words(source, profile)
        system = prompts.build_stylize_prompt(profile, self.catalog.sliders, pack, words)
        step = self._rewrite(system, text, self._budget(words), pack)
        return step, words

    def run(
        self,
        source: str,
        language: str,
        profile: Profile,
        path: str,
        neutral_override: str | None = None,
    ) -> RunResult:
        self.check_input(source)
        pack = self._pack(language)
        notes: list[Issue] = []
        found = detect_drift(source, pack, self.catalog.languages.values())
        if found:
            # A wrong text language makes the model translate; say so next to the result.
            notes.append(Issue("input_language_mismatch", {"expected": language, "found": found}))
        if profile.language and profile.language != language:
            notes.append(Issue("profile_language_mismatch", {"profile": profile.language, "text": language}))
        neutralise = path == PATH_NEUTRAL
        if neutralise and not profile.neutralization.dimensions:
            notes.append(Issue("neutral_skipped"))
            neutralise = False
        style = has_style(profile)
        if not style and not neutralise:
            raise PipelineError("no_style")

        steps: list[Step] = []
        neutral = key = None
        stylize_input = source
        if neutralise:
            key = neutral_cache_key(source, language, profile.neutralization)
            if neutral_override and neutral_override.strip():
                neutral = neutral_override.strip()
            else:
                step = self.neutralize(source, language, profile.neutralization)
                steps.append(step)
                neutral = step.text
            stylize_input = neutral
        if not style:
            # Neutralisation only: the neutral text is the result; a second call
            # with "reproduce unchanged" would cost time and change nothing.
            words = len(source.split())
            output = neutral or ""
            notes.append(Issue("neutral_only"))
        else:
            step, words = self.stylize(stylize_input, source, language, profile)
            steps.append(step)
            output = step.text
        issues = notes + check_result(source, output, words, pack, self.catalog.languages.values())
        measured = {name: {**measure_indicators(text, pack.indicators),
                           **measure(text, pack.abbreviations, min_words=40)}
                    for name, text in (("source", source), ("output", output))}
        paragraphs = len([p for p in output.split("\n\n") if p.strip()])
        issues += check_targets(measured["output"], profile.targets, paragraphs)
        issues += check_directions(measured["source"], measured["output"], profile.sliders)
        issues += find_target_conflicts(profile.sliders, profile.targets)
        used_path = PATH_NEUTRAL if neutralise else PATH_DIRECT
        return RunResult(source, language, used_path, output, neutral, key, words, issues, steps, measured)

    # -- profile creation ----------------------------------------------------

    def _json_call(self, system: str, user: str) -> dict:
        for attempt in (1, 2):
            reply = self.llm.chat(system, user, _JSON_BUDGET)
            try:
                return prompts.extract_json(clean_output(reply.text, self.catalog.languages["en"]))
            except ValueError:
                if attempt == 2:
                    raise PipelineError("analysis_invalid_json") from None
        raise AssertionError("unreachable")

    def _profile_from_model(self, data: dict, name: str, language: str | None, origin: str) -> tuple[Profile, list[Issue]]:
        candidate = {
            "format": "text-style-profile", "version": 1, "name": name, "language": language,
            "sliders": data.get("sliders") if isinstance(data.get("sliders"), dict) else {},
            "description": data.get("description") if isinstance(data.get("description"), str) else "",
            "rules": [r for r in data.get("rules", []) if isinstance(r, str)][:5]
            if isinstance(data.get("rules"), list) else [],
            "origin": origin,
        }
        try:
            return profile_from_dict(candidate, self.catalog.sliders)
        except ProfileError:
            raise PipelineError("analysis_invalid_json") from None

    def analyze(self, texts: list[str], language: str, name: str, ui_lang: str) -> tuple[Profile, list[Issue]]:
        texts = [t.strip() for t in texts if t and t.strip()]
        if not texts:
            raise PipelineError("input_empty")
        if len(texts) > MAX_REFERENCE_TEXTS:
            raise PipelineError("too_many_references", limit=MAX_REFERENCE_TEXTS)
        joined = prompts.format_references(texts)
        tokens = estimate_tokens(joined)
        if tokens > self.config.max_input_tokens:
            raise PipelineError("input_too_long", tokens=tokens, limit=self.config.max_input_tokens)
        pack = self._pack(language)
        each = [measure(t, pack.abbreviations) for t in texts]
        # Several short texts are measured together rather than not at all.
        metrics = combine(each) if all(each) else measure("\n\n".join(texts), pack.abbreviations)
        evidence = {**measure_indicators("\n\n".join(texts), pack.indicators), **metrics}
        data = self._json_call(prompts.build_analysis_prompt(self.catalog.sliders, pack, ui_lang, evidence), joined)
        profile, issues = self._profile_from_model(data, name, language, "analysis")
        issues += contradictions(profile.sliders, evidence)
        if metrics:
            evidence.pop("words", None)
            profile.metrics = {**evidence, "words_measured": metrics["words_measured"]}
            profile.targets = {k: v for k, v in metrics.items() if k in TARGET_RANGES}
        if not profile.metrics:
            issues.append(Issue("metrics_too_short", {"minimum": MIN_WORDS_FOR_METRICS}))
        return profile, issues

    def from_description(self, description: str, name: str, ui_lang: str) -> tuple[Profile, list[Issue]]:
        if not description.strip():
            raise PipelineError("input_empty")
        if estimate_tokens(description) > self.config.max_input_tokens:
            raise PipelineError("input_too_long", tokens=estimate_tokens(description),
                                limit=self.config.max_input_tokens)
        data = self._json_call(prompts.build_description_prompt(self.catalog.sliders, ui_lang), description)
        return self._profile_from_model(data, name, None, "description")

    def refine(self, pairs: list[tuple[str, str]], language: str, ui_lang: str) -> list[str]:
        pairs = [(a.strip(), b.strip()) for a, b in pairs if a.strip() and b.strip() and a.strip() != b.strip()]
        if not pairs:
            raise PipelineError("refine_no_pairs")
        joined = prompts.format_pairs(pairs[:MAX_PAIRS])
        if estimate_tokens(joined) > self.config.max_input_tokens:
            raise PipelineError("input_too_long", tokens=estimate_tokens(joined),
                                limit=self.config.max_input_tokens)
        data = self._json_call(prompts.build_refine_prompt(self._pack(language), ui_lang), joined)
        rules = data.get("rules")
        if not isinstance(rules, list):
            raise PipelineError("analysis_invalid_json")
        return [r.strip()[:MAX_RULE] for r in rules if isinstance(r, str) and r.strip()][:5]


__all__ = ["Pipeline", "PipelineError", "RunResult", "LLMError", "PATH_NEUTRAL", "PATH_DIRECT",
           "MAX_PAIRS", "neutral_cache_key", "has_style"]

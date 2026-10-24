# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Gradio application: layout, event wiring and launch.

Privacy defaults are set here, in one place: no run history in the browser,
no analytics or version check, no monitoring endpoint, no API page, a limit
on upload size, short-lived temporary files, uploads deleted after reading.
"""

from __future__ import annotations

import os

# Must be set before Gradio is imported: it disables the version check and
# the telemetry of the Hugging Face client library that Gradio uses.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import atexit  # noqa: E402
import copy  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import gradio as gr  # noqa: E402

from .. import __version__  # noqa: E402
from ..config import Config  # noqa: E402
from ..core import profile_code  # noqa: E402
from ..core.catalog import Catalog, load_catalog, load_library  # noqa: E402
from ..core.checks import find_conflicts  # noqa: E402
from ..core.documents import EXPORT_FORMATS, DocumentError, read_text, write_export  # noqa: E402
from ..core.llm import LLMClient, LLMError  # noqa: E402
from ..core.models import (  # noqa: E402
    DEFAULT_DIMENSIONS,
    NEUTRALIZATION_DIMENSIONS,
    STRENGTHS,
    CustomSlider,
    Issue,
    Neutralization,
    Profile,
    SliderType,
)
from ..core.pipeline import MAX_PAIRS, PATH_DIRECT, PATH_NEUTRAL, Pipeline, PipelineError, neutral_cache_key  # noqa: E402
from ..core.profile_code import ProfileCodeError  # noqa: E402
from ..core.profiles import (  # noqa: E402
    MAX_CUSTOM_SLIDERS,
    MAX_RULES,
    TARGET_RANGES,
    ProfileError,
    profile_from_dict,
    profile_to_dict,
)
from ..core.skill import SkillError, build_skill, write_zip  # noqa: E402
from ..i18n import Translator, data_keys, load_ui_catalogs, number  # noqa: E402
from . import security  # noqa: E402
from .session import HistoryEntry, SessionData, TempArea, delete_upload, ensure  # noqa: E402

log = logging.getLogger(__name__)

LOCALE_JS = "() => document.documentElement.lang || navigator.language || 'en'"
REFERENCE_SEPARATOR = re.compile(r"^\s*---\s*$", re.MULTILINE)
NEUTRAL_CACHE_SIZE = 5
# Editable targets: key, slider range, step, shown in percent
TARGET_FIELDS: tuple[tuple[str, float, float, float, bool], ...] = (
    ("sentence_length_mean", 3, 60, 1, False),
    ("sentence_length_sd", 0, 30, 1, False),
    ("sentences_per_paragraph", 1, 15, 0.5, False),
    ("commas_per_sentence", 0, 5, 0.1, False),
    ("question_share", 0, 100, 1, True),
    ("exclamation_share", 0, 100, 1, True),
    ("dialogue_share", 0, 100, 1, True),
)
# Rows of the measurement table after a run: key, shown in percent
MEASURE_ROWS: tuple[tuple[str, bool], ...] = (
    ("sentence_length_mean", False), ("sentences_per_paragraph", False), ("commas_per_sentence", False),
    ("question_share", True), ("exclamation_share", True), ("word_length_mean", False), ("mattr", False),
    ("personal_rate", False), ("formal_rate", False), ("familiar_rate", False), ("hedge_rate", False),
    ("nominal_rate", False), ("list_share", True),
)
KNOWN_ERRORS = (PipelineError, LLMError, DocumentError, ProfileError, ProfileCodeError, SkillError)


@dataclass
class Services:
    config: Config
    catalog: Catalog
    library: dict[str, Profile]
    pipeline: Pipeline
    tr: Translator
    temp: TempArea


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _lang(svc: Services, locale: str | None, request: gr.Request | None = None) -> str:
    if not locale and request is not None:
        locale = (request.headers.get("accept-language") or "").split(",")[0]
    return svc.tr.lang(locale)


def _error(svc: Services, exc: Exception, lang: str) -> str:
    if isinstance(exc, KNOWN_ERRORS):
        return "❌ " + svc.tr.issue(Issue(exc.code, exc.params), lang)  # type: ignore[attr-defined]
    # Unexpected: log the type only (messages may contain user text).
    log.error("unexpected error: %s", type(exc).__name__)
    return "❌ " + svc.tr.t("issue.internal_error", lang)


def _num(value: float, lang: str) -> str:
    text = f"{value:.1f}"
    return text.replace(".", ",") if lang == "de" else text


def _issues_md(svc: Services, issues: list[Issue], lang: str) -> str:
    return "\n".join(f"- ⚠️ {svc.tr.issue(i, lang)}" for i in issues)


def _resolve(svc: Services, session: SessionData, choice: str) -> Profile | None:
    kind, _, pid = (choice or "none").partition(":")
    if kind == "session":
        return session.profile
    if kind == "builtin":
        return svc.catalog.profiles.get(pid)
    if kind == "library":
        return svc.library.get(pid)
    return None


def _ui_values(svc: Services, flat: tuple) -> dict[str, int | str]:
    values: dict[str, int | str] = {}
    for i, (sid, slider) in enumerate(svc.catalog.sliders.items()):
        active, raw = flat[2 * i], flat[2 * i + 1]
        if active:
            value = slider.coerce(raw)
            if value is not None:
                values[sid] = value
    return values


def _ui_targets(svc: Services, values: tuple) -> dict[str, float]:
    """Active targets from the target fields, which follow the slider fields."""
    tvals = values[2 * len(svc.catalog.sliders):]
    targets: dict[str, float] = {}
    for i, (key, *_rest, percent) in enumerate(TARGET_FIELDS):
        if 2 * i + 1 < len(tvals) and tvals[2 * i] and tvals[2 * i + 1] is not None:
            value = float(tvals[2 * i + 1]) / (100.0 if percent else 1.0)
            low, high = TARGET_RANGES[key]
            targets[key] = min(high, max(low, value))
    return targets


def _target_updates(profile: Profile | None) -> list:
    targets = profile.targets if profile else {}
    updates = []
    for key, low, high, _step, percent in TARGET_FIELDS:
        value = targets.get(key)
        shown = value * 100 if (value is not None and percent) else value
        updates.append(gr.update(value=value is not None))
        # A target the profile does not set keeps the field's current position.
        updates.append(gr.update(value=round(min(high, max(low, shown)), 1)) if shown is not None else gr.update())
    return updates


def _slider_updates(svc: Services, profile: Profile | None) -> list:
    updates = []
    values = profile.sliders if profile else {}
    for sid, slider in svc.catalog.sliders.items():
        value = values.get(sid)
        updates.append(gr.update(value=value is not None))
        if slider.type is SliderType.STAGES:
            default = slider.stages[len(slider.stages) // 2].id
            updates.append(gr.update(value=value if isinstance(value, str) else default))
        elif slider.type is SliderType.POLAR:
            updates.append(gr.update(value=value if isinstance(value, int) else 0))
        else:
            updates.append(gr.update(value=value if isinstance(value, int) else 5))
    return updates


def _effective(svc: Services, session: SessionData, choice: str, strength: str, dims: list[str],
               flat: tuple, lang: str) -> Profile:
    """The profile as it is set right now: chosen profile plus sliders and targets in the interface."""
    base = _resolve(svc, session, choice)
    profile = copy.deepcopy(base) if base else Profile(name=svc.tr.t("profile.manual_name", lang))
    custom = {c.id for c in profile.custom_sliders}
    values = _ui_values(svc, flat)
    values.update({k: v for k, v in profile.sliders.items() if k in custom})
    profile.sliders = values
    profile.targets = _ui_targets(svc, flat)
    profile.neutralization = Neutralization(True, strength if strength in STRENGTHS else "normal",
                                            tuple(d for d in (dims or []) if d in NEUTRALIZATION_DIMENSIONS))
    profile.description = profile.description_for(lang)
    return profile


def _personal_copy(profile: Profile, name: str | None = None, lang: str = "en") -> Profile:
    """A profile the user owns: no packaged id, labels or per-language texts.

    It keeps the name the user saw, in the interface language."""
    own = copy.deepcopy(profile)
    own.name = profile.display_name(lang)
    own.id = None
    own.labels = {}
    own.descriptions = {}
    if own.origin == "builtin":
        own.origin = "manual"
    if name and name.strip():
        own.name = name.strip()[:80]
    return own


def _profile_md(svc: Services, profile: Profile | None, lang: str) -> str:
    t = svc.tr.t
    if profile is None:
        return t("profile.summary_none", lang)
    lines = [f"### {profile.display_name(lang)}"]
    language = svc.catalog.languages.get(profile.language or "")
    lines.append(t("profile.summary_language", lang,
                   language=language.endonym if language else t("profile.language_any", lang)))
    known = dict(svc.catalog.sliders)
    known.update({c.id: c.to_slider() for c in profile.custom_sliders})
    parts = []
    for sid, value in profile.sliders.items():
        slider = known.get(sid)
        if slider is None:
            continue
        name = slider.labels.get(lang, sid) if not slider.custom else slider.labels["en"]
        if slider.type is SliderType.POLAR and isinstance(value, int) and value < 0:
            name = slider.opposite_labels.get(lang) or name
        shown = t(f"stage.{sid}.{value}", lang) if isinstance(value, str) else str(abs(value))
        parts.append(f"{name} {shown}")
    lines.append(t("profile.summary_sliders", lang, sliders=", ".join(parts) or "–"))
    description = profile.description_for(lang)
    if description:
        lines.append(t("profile.summary_description", lang, description=description))
    if profile.rules:
        lines.append(t("profile.summary_rules", lang))
        lines += [f"{i}. {r}" for i, r in enumerate(profile.rules, 1)]
    if profile.custom_sliders:
        lines.append(t("profile.summary_custom", lang))
        lines += [f"{i}. {c.label}: {c.instruction}" for i, c in enumerate(profile.custom_sliders, 1)]
    if profile.targets:
        parts = [f"{t(f'measure.{k}', lang)} {_num(profile.targets[k] * (100 if k.endswith('_share') else 1), lang)}"
                 for k, *_rest in TARGET_FIELDS if k in profile.targets]
        lines.append(t("profile.summary_targets", lang, targets="; ".join(parts)))
    m = profile.metrics
    if m.get("words_measured"):
        parts = [f"{t(f'measure.{k}', lang)} {_num(m[k] * (100 if k.endswith('_share') else 1), lang)}"
                 for k, _p in MEASURE_ROWS if k in m]
        lines.append(t("profile.summary_metrics", lang, words=int(m["words_measured"]), values="; ".join(parts)))
    return "\n\n".join(lines)


def _measure_md(svc: Services, measured: dict, targets: dict, lang: str) -> str:
    """Table source | target | result for the countable features of one run."""
    t = svc.tr.t
    source, output = measured.get("source", {}), measured.get("output", {})
    if not source and not output:
        return t("measure.too_short", lang)

    def cell(values: dict, key: str, percent: bool) -> str:
        return number(values[key] * (100 if percent else 1), lang) if key in values else "–"

    rows = [f"| {t('measure.col_feature', lang)} | {t('measure.col_source', lang)} | "
            f"{t('measure.col_target', lang)} | {t('measure.col_result', lang)} |", "|---|---|---|---|"]
    for key, percent in MEASURE_ROWS:
        if key in source or key in output:
            rows.append(f"| {t(f'measure.{key}', lang)} | {cell(source, key, percent)} | "
                        f"{cell(targets, key, percent)} | {cell(output, key, percent)} |")
    return t("measure.intro", lang) + "\n\n" + "\n".join(rows)


def _history_table(svc: Services, session: SessionData, lang: str) -> dict:
    t = svc.tr.t
    headers = [t("history.col_number", lang), t("history.col_time", lang), t("history.col_profile", lang),
               t("history.col_path", lang), t("history.col_words", lang)]
    rows = [[i, e.time, e.profile, t(f"path.{e.path}", lang), len(e.output.split())]
            for i, e in enumerate(session.history, 1)]
    return {"headers": headers, "data": rows}


def _read_upload(svc: Services, path: str | None) -> str:
    try:
        return read_text(path, svc.config.max_input_tokens * 3) if path else ""
    finally:
        delete_upload(path)


# ---------------------------------------------------------------------------
# application
# ---------------------------------------------------------------------------

def build_services(config: Config) -> Services:
    catalog = load_catalog()
    library = load_library(config.profile_dir, catalog.sliders) if config.profile_dir else {}
    catalogs = load_ui_catalogs()
    for lang, extra in data_keys(catalog, library).items():
        catalogs[lang] = {**extra, **catalogs[lang]}
    temp = TempArea(Path(tempfile.mkdtemp(prefix="text-style-transfer-")), config.temp_ttl)
    atexit.register(temp.destroy)
    pipeline = Pipeline(config, catalog, LLMClient(config))
    return Services(config, catalog, library, pipeline, Translator(catalogs), temp)


def create_app(config: Config, services: Services | None = None) -> tuple[gr.Blocks, gr.I18n, Services]:
    svc = services or build_services(config)
    cat, tr = svc.catalog, svc.tr
    i18n = gr.I18n(**tr.catalogs)
    I = i18n  # noqa: E741 - short alias for static labels

    llm_event = {"api_visibility": "private", "concurrency_id": "llm",
                 "concurrency_limit": config.llm_concurrency}
    event = {"api_visibility": "private"}

    language_choices = [(p.endonym, code) for code, p in cat.languages.items()]
    profile_choices = [(I("profile.none"), "none"), (I("profile.session"), "session")]
    def sort_key(pid: str) -> tuple[bool, str]:
        label = cat.profiles[pid].labels["en"]
        return cat.profiles[pid].language is not None, label.split(" ", 1)[-1].lower()

    profile_choices += [(I(f"profile.{pid}"), f"builtin:{pid}") for pid in sorted(cat.profiles, key=sort_key)]
    profile_choices += [(I(f"profile.library.{pid}"), f"library:{pid}") for pid in svc.library]

    def on_session_end(session: SessionData | None) -> None:
        svc.temp.remove(session)

    with gr.Blocks(title="Text Style Transfer", analytics_enabled=False,
                   delete_cache=(max(60, config.temp_ttl // 2), config.temp_ttl)) as demo:
        session = gr.State(None, time_to_live=config.session_ttl, delete_callback=on_session_end)
        locale = gr.Textbox(visible=False)
        gr.Markdown(I("app.intro"))

        # Settings shared by all tabs: profile, neutralisation, sliders, targets.
        with gr.Sidebar(label=I("sidebar.title"), open=False, width=400) as sidebar:
            gr.Markdown(I("sidebar.info"))
            choice = gr.Dropdown(profile_choices, value="none", label=I("transform.profile"))
            profile_info = gr.Markdown()
            with gr.Accordion(I("transform.neutral_settings"), open=False):
                strength = gr.Radio([(I(f"strength.{s}"), s) for s in STRENGTHS], value="normal",
                                    label=I("transform.strength"))
                dims = gr.CheckboxGroup([(I(f"dim.{d}"), d) for d in NEUTRALIZATION_DIMENSIONS],
                                        value=list(DEFAULT_DIMENSIONS), label=I("transform.dimensions"))
            flat: list = []
            group_accordions: dict[str, gr.Accordion] = {}
            with gr.Accordion(I("transform.sliders"), open=False) as sliders_accordion:
                gr.Markdown(I("transform.sliders_info"))
                for gid in cat.groups:
                    with gr.Accordion(I(f"group.{gid}"), open=False) as group_accordion:
                        group_accordions[gid] = group_accordion
                        for slider in cat.sliders_in_group(gid):
                            with gr.Row():
                                active = gr.Checkbox(label=I("common.active"), value=False, scale=1, min_width=90)
                                label, info = I(f"slider.{slider.id}"), I(f"slider.{slider.id}.info")
                                if slider.type is SliderType.STAGES:
                                    comp = gr.Radio([(I(f"stage.{slider.id}.{s.id}"), s.id) for s in slider.stages],
                                                    value=slider.stages[len(slider.stages) // 2].id,
                                                    label=label, info=info, scale=6)
                                elif slider.type is SliderType.POLAR:
                                    comp = gr.Slider(-10, 10, value=0, step=1, label=label, info=info, scale=6)
                                else:
                                    comp = gr.Slider(1, 10, value=5, step=1, label=label, info=info, scale=6)
                            flat += [active, comp]
                            # Moving a slider is a clear intent; requiring a second
                            # click on "active" made settings silently ineffective.
                            comp.input(lambda: True, None, [active], api_visibility="private", queue=False)
            tflat: list = []
            with gr.Accordion(I("targets.title"), open=False) as targets_accordion:
                gr.Markdown(I("targets.info"))
                for key, low, high, step, _percent in TARGET_FIELDS:
                    with gr.Row():
                        active = gr.Checkbox(label=I("common.active"), value=False, scale=1, min_width=90)
                        comp = gr.Slider(low, high, value=(low + high) / 2, step=step,
                                         label=I(f"measure.{key}"), scale=6)
                    tflat += [active, comp]
                    comp.input(lambda: True, None, [active], api_visibility="private", queue=False)

        with gr.Tabs():
            # ---------------------------------------------------------- guided: own text -> skill
            with gr.Tab(I("tab.wizard")):
                with gr.Walkthrough(selected=0) as wizard:
                    with gr.Step(I("wizard.step1"), id=0):
                        gr.Markdown(I("wizard.step1_info"))
                        wiz_text = gr.Textbox(label=I("wizard.text"), lines=12, info=I("copy.references_info"))
                        wiz_upload = gr.File(label=I("copy.upload"), file_types=[".txt", ".md", ".docx"],
                                             file_count="multiple", type="filepath")
                        with gr.Row():
                            wiz_lang = gr.Dropdown(language_choices, value="en", label=I("common.text_language"))
                            wiz_name = gr.Textbox(label=I("wizard.name"), placeholder=I("wizard.name_ph"))
                        wiz_analyze = gr.Button(I("copy.analyze"), variant="primary")
                        wiz_status1 = gr.Markdown()
                    with gr.Step(I("wizard.step2"), id=1):
                        gr.Markdown(I("wizard.step2_info"))
                        wiz_summary = gr.Markdown()
                        wiz_refresh = gr.Button(I("profile.refresh"))
                        wiz_desc = gr.Textbox(label=I("profile.edit_description"), lines=4)
                        wiz_rules = gr.Textbox(label=I("profile.edit_rules"), lines=5, info=I("profile.edit_rules_info"))
                        wiz_apply_text = gr.Button(I("profile.apply_text"))
                        wiz_status2 = gr.Markdown()
                        with gr.Row():
                            wiz_back2 = gr.Button(I("wizard.back"))
                            wiz_next2 = gr.Button(I("wizard.to_step3"), variant="primary")
                    with gr.Step(I("wizard.step3"), id=2):
                        gr.Markdown(I("wizard.step3_info"))
                        wiz_test = gr.Textbox(label=I("wizard.test_text"), lines=8, placeholder=I("wizard.test_ph"))
                        with gr.Row():
                            wiz_direct = gr.Button(I("transform.run_direct"), variant="primary")
                            wiz_neutral = gr.Button(I("transform.run_neutral"))
                        wiz_status3 = gr.Markdown()
                        with gr.Row():
                            wiz_output = gr.Textbox(label=I("wizard.result"), lines=8, buttons=["copy"], interactive=False)
                            wiz_previous = gr.Textbox(label=I("wizard.previous"), lines=8, interactive=False)
                        wiz_warnings = gr.Markdown()
                        with gr.Row():
                            wiz_table = gr.Markdown()
                            wiz_prev_table = gr.Markdown()
                        with gr.Row():
                            wiz_back3 = gr.Button(I("wizard.back"))
                            wiz_next3 = gr.Button(I("wizard.to_step4"), variant="primary")
                    with gr.Step(I("wizard.step4"), id=3):
                        gr.Markdown(I("wizard.step4_info"))
                        wiz_skill_btn = gr.Button(I("profile.export_skill"), variant="primary")
                        wiz_skill_file = gr.File(label=I("profile.skill_file"), interactive=False)
                        gr.Markdown(I("profile.skill_info"))
                        wiz_code_btn = gr.Button(I("profile.show_code"))
                        wiz_code = gr.Textbox(label=I("profile.code"), lines=3, buttons=["copy"], interactive=False)
                        wiz_status4 = gr.Markdown()
                        wiz_back4 = gr.Button(I("wizard.back"))

            # ---------------------------------------------------------- transform
            with gr.Tab(I("tab.transform")):
                with gr.Row():
                    with gr.Column(scale=3):
                        source = gr.Textbox(label=I("transform.input"), lines=10, placeholder=I("transform.input_ph"))
                        upload = gr.File(label=I("transform.upload"), file_types=[".txt", ".md", ".docx"], type="filepath")
                    with gr.Column(scale=2):
                        text_lang = gr.Dropdown(language_choices, value="en", label=I("common.text_language"),
                                                info=I("common.text_language_info"))
                        gr.Markdown(I("transform.settings_hint"))
                        with gr.Row():
                            run_neutral = gr.Button(I("transform.run_neutral"), variant="primary")
                            run_direct = gr.Button(I("transform.run_direct"))
                        status = gr.Markdown()
                with gr.Row():
                    neutral_box = gr.Textbox(label=I("transform.neutral"), lines=8, info=I("transform.neutral_info"))
                    output_box = gr.Textbox(label=I("transform.output"), lines=8, buttons=["copy"])
                warnings = gr.Markdown()
                measure_md = gr.Markdown()
                with gr.Row():
                    export_fmt = gr.Radio(list(EXPORT_FORMATS), value="txt", label=I("export.format"))
                    export_both = gr.Checkbox(label=I("export.with_original"), value=False)
                    export_btn = gr.Button(I("export.button"))
                export_file = gr.File(label=I("export.file"), interactive=False)

            # ---------------------------------------------------------- copy style
            with gr.Tab(I("tab.copy")):
                gr.Markdown(I("copy.intro"))
                with gr.Row():
                    with gr.Column():
                        refs = gr.Textbox(label=I("copy.references"), lines=12, info=I("copy.references_info"))
                        refs_upload = gr.File(label=I("copy.upload"), file_types=[".txt", ".md", ".docx"],
                                              file_count="multiple", type="filepath")
                        refs_lang = gr.Dropdown(language_choices, value="en", label=I("common.text_language"))
                        refs_name = gr.Textbox(label=I("common.profile_name"), value="")
                        analyze_btn = gr.Button(I("copy.analyze"), variant="primary")
                    with gr.Column():
                        describe = gr.Textbox(label=I("copy.description"), lines=6, placeholder=I("copy.description_ph"))
                        describe_name = gr.Textbox(label=I("common.profile_name"), value="")
                        describe_btn = gr.Button(I("copy.describe"))
                copy_status = gr.Markdown()

            # ---------------------------------------------------------- refine
            with gr.Tab(I("tab.refine")):
                gr.Markdown(I("refine.intro"))
                with gr.Row():
                    pair_a = gr.Textbox(label=I("refine.original"), lines=6)
                    pair_b = gr.Textbox(label=I("refine.edited"), lines=6)
                with gr.Row():
                    add_pair = gr.Button(I("refine.add"))
                    clear_pairs = gr.Button(I("refine.clear"))
                    refine_lang = gr.Dropdown(language_choices, value="en", label=I("common.text_language"))
                    refine_btn = gr.Button(I("refine.run"), variant="primary")
                pairs_md = gr.Markdown()
                with gr.Row():
                    rule_no = gr.Number(label=I("refine.rule_number"), value=1, precision=0, minimum=1)
                    remove_rule = gr.Button(I("refine.remove_rule"))
                refine_status = gr.Markdown()

            # ---------------------------------------------------------- profile
            with gr.Tab(I("tab.profile")):
                summary = gr.Markdown()
                refresh = gr.Button(I("profile.refresh"))
                with gr.Row():
                    with gr.Column():
                        own_name = gr.Textbox(label=I("common.profile_name"))
                        code_btn = gr.Button(I("profile.show_code"))
                        code_out = gr.Textbox(label=I("profile.code"), lines=3, buttons=["copy"], interactive=False)
                        json_btn = gr.Button(I("profile.download_json"))
                        json_file = gr.File(label=I("export.file"), interactive=False)
                        skill_btn = gr.Button(I("profile.export_skill"), variant="primary")
                        skill_file = gr.File(label=I("profile.skill_file"), interactive=False)
                        gr.Markdown(I("profile.skill_info"))
                    with gr.Column():
                        code_in = gr.Textbox(label=I("profile.code_input"), lines=3, info=I("profile.code_input_info"))
                        load_code = gr.Button(I("profile.load_code"))
                        json_upload = gr.File(label=I("profile.upload_json"), file_types=[".json"], type="filepath")
                with gr.Accordion(I("profile.edit_title"), open=False):
                    desc_box = gr.Textbox(label=I("profile.edit_description"), lines=4)
                    rules_box = gr.Textbox(label=I("profile.edit_rules"), lines=6, info=I("profile.edit_rules_info"))
                    apply_text = gr.Button(I("profile.apply_text"))
                with gr.Accordion(I("custom.title"), open=False):
                    gr.Markdown(I("custom.intro"))
                    with gr.Row():
                        cs_type = gr.Radio([(I("custom.type_intensity"), "intensity"), (I("custom.type_polar"), "polar")],
                                           value="intensity", label=I("custom.type"))
                        cs_value = gr.Slider(-10, 10, value=5, step=1, label=I("custom.value"), info=I("custom.value_info"))
                    with gr.Row():
                        cs_label = gr.Textbox(label=I("custom.label"))
                        cs_instruction = gr.Textbox(label=I("custom.instruction"), lines=2)
                    with gr.Row():
                        cs_opp_label = gr.Textbox(label=I("custom.opposite_label"))
                        cs_opp_instruction = gr.Textbox(label=I("custom.opposite_instruction"), lines=2)
                    with gr.Row():
                        cs_add = gr.Button(I("custom.add"))
                        cs_no = gr.Number(label=I("custom.number"), value=1, precision=0, minimum=1)
                        cs_remove = gr.Button(I("custom.remove"))
                profile_status = gr.Markdown()

            # ---------------------------------------------------------- history
            with gr.Tab(I("tab.history")):
                gr.Markdown(I("history.intro"))
                table = gr.Dataframe(value={"headers": ["#", "", "", "", ""], "data": []}, interactive=False, wrap=True)
                with gr.Row():
                    hist_no = gr.Number(label=I("history.entry"), value=1, precision=0, minimum=1)
                    hist_show = gr.Button(I("history.show"))
                    hist_clear = gr.Button(I("history.clear"))
                with gr.Row():
                    hist_source = gr.Textbox(label=I("transform.input"), lines=8, interactive=False)
                    hist_output = gr.Textbox(label=I("transform.output"), lines=8, interactive=False, buttons=["copy"])

            # ---------------------------------------------------------- about
            with gr.Tab(I("tab.about")):
                gr.Markdown(I("about.text"))
                gr.Markdown(I("about.endpoint") + f" `{config.llm_host}` · " + f"v{__version__}")
                if config.privacy_notice_file:
                    gr.Markdown(config.privacy_notice_file.read_text(encoding="utf-8"))
                else:
                    gr.Markdown(I("about.no_notice"))

        profile_inputs = [choice, strength, dims, session, *flat, *tflat]

        # -------------------------------------------------------------- handlers
        def on_load(loc, request: gr.Request):
            lang = _lang(svc, loc, request)
            raw = loc or (request.headers.get("accept-language") or "").split(",")[0]
            base = raw.lower().replace("_", "-").split("-")[0]
            # The interface exists in two languages, texts in six: a French
            # browser gets an English interface but French as text language.
            text_default = base if base in cat.languages else lang
            s = SessionData()
            # Store the resolved language, not the raw input: if the browser
            # reported nothing, the Accept-Language header decides here, and
            # every later event uses this value.
            return (lang, gr.update(value=text_default), gr.update(value=text_default), gr.update(value=text_default),
                    _history_table(svc, s, lang), _profile_md(svc, None, lang), gr.update(value=text_default))

        def on_upload(path, loc):
            lang = _lang(svc, loc)
            try:
                return _read_upload(svc, path), None, ""
            except DocumentError as exc:
                return gr.update(), None, _error(svc, exc, lang)

        def on_refs_upload(paths, current, loc):
            lang = _lang(svc, loc)
            texts, message = [current.strip()] if current and current.strip() else [], ""
            for path in paths or []:
                try:
                    texts.append(_read_upload(svc, path))
                except DocumentError as exc:
                    message = _error(svc, exc, lang)
            return "\n\n---\n\n".join(texts), None, message

        def apply_profile(choice_value, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            profile = _resolve(svc, s, choice_value)
            info = ""
            if choice_value == "session" and profile is None:
                info = svc.tr.t("profile.session_empty", lang)
            elif profile is not None:
                info = profile.description_for(lang)
            # The text language describes the text, not the profile, so it is
            # never changed here; a profile made for another language is
            # reported next to the result instead.
            extra = [gr.update(), gr.update(), info]
            if profile is not None:
                extra = [gr.update(value=profile.neutralization.strength),
                         gr.update(value=list(profile.neutralization.dimensions)),
                         info]
            texts = [profile.description_for(lang) if profile else "", "\n".join(profile.rules) if profile else ""]
            # Open the areas that contain settings, so that they can be seen without searching.
            used = set(profile.sliders) if profile else set()
            groups = [gr.update(open=True) if any(sl.id in used for sl in cat.sliders_in_group(gid)) else gr.update()
                      for gid in cat.groups]
            opened = [gr.update(open=True) if used else gr.update(), *groups,
                      gr.update(open=True) if profile and profile.targets else gr.update()]
            summary_md = _profile_md(svc, profile, lang)
            return [*_slider_updates(svc, profile), *_target_updates(profile), *extra,
                    summary_md, *opened, summary_md, *texts, *texts, s]

        def ensure_preset_values(choice_value, s, *values):
            """First step of every run: make sure the chosen profile's values are in the sliders.

            Selecting a profile writes into dozens of components. If a run is
            started immediately, the browser may still send the old values and
            the prompt would contain no style feature at all. This only
            intervenes if none of the profile's sliders is active, which is
            exactly what the race looks like; values the user adjusted by hand
            after selecting the profile are left alone.
            """
            unchanged = [gr.update() for _ in (*flat, *tflat)]
            profile = _resolve(svc, ensure(s), choice_value)
            if profile is None or not (profile.sliders or profile.targets):
                return unchanged
            if any(sid in _ui_values(svc, values) for sid in profile.sliders) or _ui_targets(svc, values):
                return unchanged
            log.info("profile values were not yet in the sliders and were applied before the run")
            return [*_slider_updates(svc, profile), *_target_updates(profile)]

        def execute(path, src, neutral_text, lang_code, choice_value, strength_value, dims_value, s, values, lang):
            """One run, shared by the tabs. Returns (result, issues_md, status, measure_md) or raises."""
            profile = _effective(svc, s, choice_value, strength_value, dims_value, tuple(values), lang)
            override = None
            if path == PATH_NEUTRAL:
                key = neutral_cache_key(src or "", lang_code, profile.neutralization)
                if key == s.last_neutral_key and (neutral_text or "").strip():
                    override = neutral_text  # reuse, including the user's own corrections
                elif key in s.neutral_cache:
                    override = s.neutral_cache[key]
            result = svc.pipeline.run(src or "", lang_code, profile, path, override)
            if result.neutral_key:
                s.neutral_cache[result.neutral_key] = result.neutral or ""
                while len(s.neutral_cache) > NEUTRAL_CACHE_SIZE:
                    s.neutral_cache.pop(next(iter(s.neutral_cache)))
                s.last_neutral_key = result.neutral_key
            issues = list(result.issues)
            issues += [Issue("conflict", {"hint": svc.tr.t(f"conflict.{c.a}.{c.b}", lang)})
                       for c in find_conflicts(profile.sliders, cat.conflicts)]
            s.history.append(HistoryEntry(datetime.now().strftime("%H:%M"), profile.display_name(lang),
                                          result.path, lang_code, result.source, result.neutral, result.output))
            del s.history[:-config.history_size]
            seconds = sum(st.seconds for st in result.steps)
            tokens = sum((st.prompt_tokens or 0) + (st.completion_tokens or 0) for st in result.steps)
            done = svc.tr.t("status.done", lang, steps=len(result.steps), seconds=_num(seconds, lang),
                            tokens=tokens or "?", words=len(result.output.split()), target=result.target_words)
            return result, _issues_md(svc, issues, lang), "✅ " + done, _measure_md(svc, result.measured, profile.targets, lang)

        def make_run(path):
            def run(src, neutral_text, lang_code, choice_value, strength_value, dims_value, s, *rest):
                *values, loc = rest
                lang = _lang(svc, loc)
                s = ensure(s)
                try:
                    result, issues_md, done, table_md = execute(path, src, neutral_text, lang_code, choice_value,
                                                                strength_value, dims_value, s, values, lang)
                except Exception as exc:  # noqa: BLE001 - shown as a message, never as a traceback
                    return gr.update(), gr.update(), "", _error(svc, exc, lang), s, gr.update(), ""
                neutral_out = result.neutral if result.neutral is not None else gr.update()
                return (result.output, neutral_out, issues_md, done, s, _history_table(svc, s, lang), table_md)
            return run

        def make_wizard_run(path):
            def run(src, lang_code, choice_value, strength_value, dims_value, s, *rest):
                *values, loc = rest
                lang = _lang(svc, loc)
                s = ensure(s)
                try:
                    result, issues_md, done, table_md = execute(path, src, "", lang_code, choice_value,
                                                                strength_value, dims_value, s, values, lang)
                except Exception as exc:  # noqa: BLE001
                    return gr.update(), "", _error(svc, exc, lang), s, gr.update(), gr.update(), gr.update(), gr.update()
                previous = s.wizard_previous or ("", "")
                s.wizard_previous = (result.output, table_md)
                return (result.output, issues_md, done, s, table_md, previous[0], previous[1], _history_table(svc, s, lang))
            return run

        run_outputs = [output_box, neutral_box, warnings, status, session, table, measure_md]
        run_inputs = [source, neutral_box, text_lang, choice, strength, dims, session, *flat, *tflat, locale]

        def do_export(output, src, fmt, both, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            if not (output or "").strip():
                return None, svc.tr.t("export.nothing", lang), s
            try:
                path = write_export(svc.temp.folder(s), fmt, output, src if both else None,
                                    (svc.tr.t("export.original", lang), svc.tr.t("export.result", lang)))
            except DocumentError as exc:
                return None, _error(svc, exc, lang), s
            return str(path), "", s

        def set_session_profile(s, profile: Profile, issues: list[Issue], lang: str, message_key: str):
            s.profile = profile
            text = "✅ " + svc.tr.t(message_key, lang) + "\n\n" + _profile_md(svc, profile, lang)
            if issues:
                text += "\n\n" + _issues_md(svc, issues, lang)
            return text

        def do_analyze(text, lang_code, name, s, loc, next_key="copy.next_steps"):
            lang = _lang(svc, loc)
            s = ensure(s)
            texts = [t for t in REFERENCE_SEPARATOR.split(text or "") if t.strip()]
            try:
                profile, issues = svc.pipeline.analyze(texts, lang_code,
                                                       name or svc.tr.t("copy.default_name", lang), lang)
            except Exception as exc:  # noqa: BLE001
                return _error(svc, exc, lang), s, gr.update()
            text = set_session_profile(s, profile, issues, lang, "copy.done")
            return text + "\n\n" + svc.tr.t(next_key, lang), s, gr.update(value="session")

        def do_describe(text, name, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            try:
                profile, issues = svc.pipeline.from_description(text or "",
                                                                name or svc.tr.t("copy.default_name", lang), lang)
            except Exception as exc:  # noqa: BLE001
                return _error(svc, exc, lang), s, gr.update()
            return set_session_profile(s, profile, issues, lang, "copy.done"), s, gr.update(value="session")

        def pairs_markdown(s, lang):
            if not s.pairs:
                return svc.tr.t("refine.no_pairs", lang)
            lines = [svc.tr.t("refine.pairs", lang, count=len(s.pairs), limit=MAX_PAIRS)]
            lines += [f"{i}. {a[:80]}… → {b[:80]}…" for i, (a, b) in enumerate(s.pairs, 1)]
            return "\n".join(lines)

        def do_add_pair(a, b, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            if not (a or "").strip() or not (b or "").strip() or a.strip() == b.strip():
                return gr.update(), gr.update(), pairs_markdown(s, lang), svc.tr.t("refine.pair_invalid", lang), s
            if len(s.pairs) >= MAX_PAIRS:
                return gr.update(), gr.update(), pairs_markdown(s, lang), svc.tr.t("refine.pair_limit", lang, limit=MAX_PAIRS), s
            s.pairs.append((a.strip(), b.strip()))
            return "", "", pairs_markdown(s, lang), "", s

        def do_clear_pairs(s, loc):
            s = ensure(s)
            s.pairs = []
            return pairs_markdown(s, _lang(svc, loc)), s

        def own_profile(s, choice_value, strength_value, dims_value, values, lang) -> tuple[Profile, str]:
            """The session's own profile, brought up to date with the current sliders and targets.

            It is always rebuilt from what the interface shows: adjustments made
            after an analysis must survive editing rules or description.
            Returns a note if a packaged profile became, or replaced, the own profile.
            """
            note = ""
            if choice_value != "session":
                note = svc.tr.t("profile.own_replaced" if s.profile is not None else "profile.own_created", lang)
            s.profile = _personal_copy(_effective(svc, s, choice_value, strength_value, dims_value, values, lang), lang=lang)
            return s.profile, note

        def do_refine(lang_code, choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            try:
                rules = svc.pipeline.refine(s.pairs, lang_code, lang)
            except Exception as exc:  # noqa: BLE001
                return _error(svc, exc, lang), s, gr.update()
            profile, note = own_profile(s, choice_value, strength_value, dims_value, tuple(values), lang)
            added = [r for r in rules if r not in profile.rules][:max(0, MAX_RULES - len(profile.rules))]
            profile.rules += added
            profile.origin = "refined"
            text = svc.tr.t("refine.done", lang, count=len(added)) + (" " + note if note else "")
            text += "\n\n" + _profile_md(svc, profile, lang)
            return "✅ " + text, s, gr.update(value="session")

        def do_remove_rule(number, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            index = int(number or 0) - 1
            if s.profile is None or not 0 <= index < len(s.profile.rules):
                return svc.tr.t("refine.rule_missing", lang), s
            s.profile.rules.pop(index)
            return _profile_md(svc, s.profile, lang), s

        def do_summary(choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            return _profile_md(svc, _effective(svc, s, choice_value, strength_value, dims_value, tuple(values), lang), lang), s

        def do_code(name, choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            profile = _personal_copy(_effective(svc, s, choice_value, strength_value, dims_value, tuple(values), lang), name, lang)
            try:
                return profile_code.encode(profile_to_dict(profile)), "", s
            except ProfileCodeError as exc:
                return "", _error(svc, exc, lang), s

        def do_json(name, choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            profile = _personal_copy(_effective(svc, s, choice_value, strength_value, dims_value, tuple(values), lang), name, lang)
            import json as _json
            folder = svc.temp.folder(s) / datetime.now().strftime("%Y%m%d%H%M%S%f")
            folder.mkdir()
            safe = re.sub(r"[^A-Za-z0-9_-]+", "-", profile.name).strip("-") or "profile"
            path = folder / f"{safe[:40]}.json"
            path.write_text(_json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2), encoding="utf-8")
            return str(path), "", s

        def do_apply_text(description, rules_text, choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            profile, note = own_profile(s, choice_value, strength_value, dims_value, tuple(values), lang)
            data = profile_to_dict(profile)
            data["description"] = description or ""
            data["rules"] = [line.strip() for line in (rules_text or "").splitlines() if line.strip()]
            edited, issues = profile_from_dict(data, cat.sliders)
            edited.custom_sliders = profile.custom_sliders
            s.profile = _personal_copy(edited, lang=lang)
            text = "✅ " + svc.tr.t("profile.text_applied", lang) + (" " + note if note else "")
            if issues:
                text += "\n\n" + _issues_md(svc, issues, lang)
            return text, s, gr.update(value="session")

        def do_skill(name, choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            effective = _effective(svc, s, choice_value, strength_value, dims_value, tuple(values), lang)
            profile = _personal_copy(effective, name, lang)
            try:
                export = build_skill(profile, cat, profile.name)
            except SkillError as exc:
                return None, _error(svc, exc, lang), s
            folder = svc.temp.folder(s) / datetime.now().strftime("%Y%m%d%H%M%S%f")
            path = write_zip(export, folder)
            text = "✅ " + svc.tr.t("profile.skill_done", lang, name=export.name)
            if export.issues:
                text += "\n\n" + _issues_md(svc, export.issues, lang)
            return str(path), text, s

        def load_profile_data(data, s, lang):
            profile, issues = profile_from_dict(data, cat.sliders)
            profile = _personal_copy(profile, lang=lang)
            notice = svc.tr.t("profile.loaded_review", lang) if (profile.description or profile.rules or profile.custom_sliders) else ""
            text = set_session_profile(s, profile, issues, lang, "profile.loaded")
            return text + ("\n\n" + notice if notice else "")

        def do_load_code(code, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            try:
                text = load_profile_data(profile_code.decode(code or ""), s, lang)
            except Exception as exc:  # noqa: BLE001
                return _error(svc, exc, lang), s, gr.update()
            return text, s, gr.update(value="session")

        def do_upload_json(path, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            import json as _json
            try:
                if not path:
                    return gr.update(), s, gr.update(), None
                raw = Path(path).read_bytes()
                delete_upload(path)
                if len(raw) > profile_code.MAX_JSON_BYTES:
                    raise ProfileCodeError("code_too_large")
                text = load_profile_data(_json.loads(raw.decode("utf-8")), s, lang)
            except (ValueError, UnicodeDecodeError) as exc:
                delete_upload(path)
                if not isinstance(exc, KNOWN_ERRORS):
                    exc = ProfileError("profile_not_object")
                return _error(svc, exc, lang), s, gr.update(), None
            return text, s, gr.update(value="session"), None

        def do_add_custom(stype, value, label, instruction, opp_label, opp_instruction,
                          choice_value, strength_value, dims_value, s, *rest):
            *values, loc = rest
            lang = _lang(svc, loc)
            s = ensure(s)
            if not (label or "").strip() or not (instruction or "").strip():
                return svc.tr.t("custom.missing", lang), s, gr.update()
            if stype == "polar" and (not (opp_label or "").strip() or not (opp_instruction or "").strip()):
                return svc.tr.t("custom.missing_opposite", lang), s, gr.update()
            profile, note = own_profile(s, choice_value, strength_value, dims_value, tuple(values), lang)
            if len(profile.custom_sliders) >= MAX_CUSTOM_SLIDERS:
                return svc.tr.t("custom.limit", lang, limit=MAX_CUSTOM_SLIDERS), s, gr.update()
            number = 1 + max([int(c.id.rsplit("_", 1)[1]) for c in profile.custom_sliders] or [0])
            custom = CustomSlider(id=f"custom_{number}", type=SliderType(stype), label=label.strip()[:60],
                                  instruction=instruction.strip()[:500], opposite_label=(opp_label or "").strip()[:60],
                                  opposite_instruction=(opp_instruction or "").strip()[:500])
            coerced = custom.to_slider().coerce(value)
            if coerced is None:
                return svc.tr.t("custom.value_invalid", lang), s, gr.update()
            profile.custom_sliders.append(custom)
            profile.sliders[custom.id] = coerced
            return (note + "\n\n" if note else "") + _profile_md(svc, profile, lang), s, gr.update(value="session")

        def do_remove_custom(number, s, loc):
            lang = _lang(svc, loc)
            s = ensure(s)
            index = int(number or 0) - 1
            if s.profile is None or not 0 <= index < len(s.profile.custom_sliders):
                return svc.tr.t("custom.not_found", lang), s
            removed = s.profile.custom_sliders.pop(index)
            s.profile.sliders.pop(removed.id, None)
            return _profile_md(svc, s.profile, lang), s

        def do_history_show(number, s, loc):
            s = ensure(s)
            index = int(number or 0) - 1
            if not 0 <= index < len(s.history):
                return "", svc.tr.t("history.missing", _lang(svc, loc))
            return s.history[index].source, s.history[index].output

        def do_history_clear(s, loc):
            s = ensure(s)
            s.history = []
            return _history_table(svc, s, _lang(svc, loc)), "", "", s

        # -------------------------------------------------------------- wiring
        apply_outputs = [*flat, *tflat, strength, dims, profile_info, summary, sliders_accordion,
                         *group_accordions.values(), targets_accordion, wiz_summary, wiz_desc, wiz_rules,
                         desc_box, rules_box, session]
        demo.load(None, None, [locale], js=LOCALE_JS).then(
            on_load, [locale], [locale, text_lang, refs_lang, refine_lang, table, summary, wiz_lang], **event)
        demo.unload(svc.temp.sweep)
        upload.upload(on_upload, [upload, locale], [source, upload, status], **event)
        refs_upload.upload(on_refs_upload, [refs_upload, refs, locale], [refs, refs_upload, copy_status], **event)
        choice.input(apply_profile, [choice, session, locale], apply_outputs, **event)

        for button, path in ((run_neutral, PATH_NEUTRAL), (run_direct, PATH_DIRECT)):
            button.click(ensure_preset_values, [choice, session, *flat, *tflat], [*flat, *tflat], **event).then(
                lambda loc: "⏳ " + svc.tr.t("status.running", _lang(svc, loc)), [locale], [status], **event).then(
                make_run(path), run_inputs, run_outputs, **llm_event)

        export_btn.click(do_export, [output_box, source, export_fmt, export_both, session, locale],
                         [export_file, status, session], **event)
        analyze_btn.click(do_analyze, [refs, refs_lang, refs_name, session, locale],
                          [copy_status, session, choice], **llm_event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        describe_btn.click(do_describe, [describe, describe_name, session, locale],
                           [copy_status, session, choice], **llm_event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        add_pair.click(do_add_pair, [pair_a, pair_b, session, locale], [pair_a, pair_b, pairs_md, refine_status, session], **event)
        clear_pairs.click(do_clear_pairs, [session, locale], [pairs_md, session], **event)
        refine_btn.click(do_refine, [refine_lang, choice, strength, dims, session, *flat, *tflat, locale],
                         [refine_status, session, choice], **llm_event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        remove_rule.click(do_remove_rule, [rule_no, session, locale], [refine_status, session], **event)
        refresh.click(do_summary, [*profile_inputs, locale], [summary, session], **event)
        code_btn.click(do_code, [own_name, *profile_inputs, locale], [code_out, profile_status, session], **event)
        json_btn.click(do_json, [own_name, *profile_inputs, locale], [json_file, profile_status, session], **event)
        apply_text.click(do_apply_text, [desc_box, rules_box, *profile_inputs, locale],
                         [profile_status, session, choice], **event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        skill_btn.click(do_skill, [own_name, *profile_inputs, locale], [skill_file, profile_status, session], **event)
        load_code.click(do_load_code, [code_in, session, locale], [profile_status, session, choice], **event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        json_upload.upload(do_upload_json, [json_upload, session, locale],
                           [profile_status, session, choice, json_upload], **event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        cs_add.click(do_add_custom, [cs_type, cs_value, cs_label, cs_instruction, cs_opp_label, cs_opp_instruction,
                                     *profile_inputs, locale], [profile_status, session, choice], **event)
        cs_remove.click(do_remove_custom, [cs_no, session, locale], [profile_status, session], **event)
        hist_show.click(do_history_show, [hist_no, session, locale], [hist_source, hist_output], **event)
        hist_clear.click(do_history_clear, [session, locale], [table, hist_source, hist_output, session], **event)

        # -------------------------------------------------------------- guided tab
        def to_step(step: int, open_sidebar: bool = False):
            def go():
                return (gr.Walkthrough(selected=step), gr.Sidebar(open=True)) if open_sidebar else gr.Walkthrough(selected=step)
            return go

        def wiz_analyze_fn(text, lang_code, name, s, loc):
            message, s, choice_update = do_analyze(text, lang_code, name, s, loc, "wizard.next_steps")
            ok = isinstance(choice_update, dict) and choice_update.get("value") == "session"
            step = gr.Walkthrough(selected=1) if ok else gr.update()
            sidebar_update = gr.Sidebar(open=True) if ok else gr.update()
            return message, s, choice_update, step, sidebar_update

        wiz_upload.upload(on_refs_upload, [wiz_upload, wiz_text, locale], [wiz_text, wiz_upload, wiz_status1], **event)
        wiz_analyze.click(wiz_analyze_fn, [wiz_text, wiz_lang, wiz_name, session, locale],
                          [wiz_status1, session, choice, wizard, sidebar], **llm_event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        wiz_refresh.click(do_summary, [*profile_inputs, locale], [wiz_summary, session], **event)
        wiz_apply_text.click(do_apply_text, [wiz_desc, wiz_rules, *profile_inputs, locale],
                             [wiz_status2, session, choice], **event).then(
            apply_profile, [choice, session, locale], apply_outputs, **event)
        wiz_inputs = [wiz_test, wiz_lang, choice, strength, dims, session, *flat, *tflat, locale]
        wiz_outputs = [wiz_output, wiz_warnings, wiz_status3, session, wiz_table, wiz_previous, wiz_prev_table, table]
        for button, path in ((wiz_direct, PATH_DIRECT), (wiz_neutral, PATH_NEUTRAL)):
            button.click(ensure_preset_values, [choice, session, *flat, *tflat], [*flat, *tflat], **event).then(
                lambda loc: "⏳ " + svc.tr.t("status.running", _lang(svc, loc)), [locale], [wiz_status3], **event).then(
                make_wizard_run(path), wiz_inputs, wiz_outputs, **llm_event)
        wiz_skill_btn.click(do_skill, [wiz_name, *profile_inputs, locale], [wiz_skill_file, wiz_status4, session], **event)
        wiz_code_btn.click(do_code, [wiz_name, *profile_inputs, locale], [wiz_code, wiz_status4, session], **event)
        wiz_next2.click(to_step(2), None, wizard, **event)
        wiz_next3.click(to_step(3), None, wizard, **event)
        wiz_back2.click(to_step(0), None, wizard, **event)
        wiz_back3.click(to_step(1, open_sidebar=True), None, [wizard, sidebar], **event)
        wiz_back4.click(to_step(2), None, wizard, **event)

    return demo, i18n, svc


def launch(config: Config) -> None:
    demo, i18n, _ = create_app(config)
    demo.queue(default_concurrency_limit=16)
    try:
        _launch(demo, i18n, config)
    except KeyboardInterrupt:
        # A stop signal that arrives while launch() is still finishing its start-up
        # checks reaches this point instead of Gradio's own handling.
        demo.close()


def _launch(demo: gr.Blocks, i18n: gr.I18n, config: Config) -> None:
    demo.launch(
        server_name=config.host,
        server_port=config.port,
        root_path=config.root_path or None,
        i18n=i18n,
        theme=gr.themes.Default(),
        show_error=False,
        run_history=False,
        enable_monitoring=False,
        footer_links=["gradio", "settings"],
        mcp_server=False,
        pwa=False,
        ssr_mode=False,
        max_file_size=config.max_upload_bytes,
        auth_dependency=security.auth_dependency(config),
        app_kwargs={"middleware": security.middleware(config)},
    )

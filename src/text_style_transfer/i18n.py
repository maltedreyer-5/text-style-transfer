# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""User-interface texts in English and German.

One catalog feeds two paths:
- static labels are handed to Gradio's I18n and translated in the browser;
- messages with parameters are formatted here, on the server, in the
  language the browser reports with each event.

Gradio's I18n objects must never be formatted or concatenated with each
other: .format() on them silently returns the untranslated placeholder, and
only the first placeholder of a string is translated. Use t() for anything
with parameters.
"""

from __future__ import annotations

import json
import string
from importlib import resources

from .core.catalog import Catalog
from .core.models import UI_LANGUAGES, Issue, SliderType

FALLBACK = "en"
LANGUAGE_PARAMS = ("expected", "found", "profile", "text")
NAMED_PARAMS = {"metric": "measure", "slider": "slider"}


def number(value: float, lang: str) -> str:
    text = f"{value:.1f}"
    return text.replace(".", ",") if lang == "de" else text


def load_ui_catalogs() -> dict[str, dict[str, str]]:
    catalogs = {}
    for lang in UI_LANGUAGES:
        path = resources.files("text_style_transfer").joinpath("data", "ui", f"{lang}.json")
        catalogs[lang] = json.loads(path.read_text(encoding="utf-8"))
    return catalogs


def data_keys(catalog: Catalog, library: dict | None = None) -> dict[str, dict[str, str]]:
    """Texts that come from the packaged data (slider, group, profile labels)."""
    out: dict[str, dict[str, str]] = {lang: {} for lang in UI_LANGUAGES}
    for lang in UI_LANGUAGES:
        d = out[lang]
        for s in catalog.sliders.values():
            if s.type is SliderType.POLAR:
                d[f"slider.{s.id}"] = f"{s.labels[lang]} ↔ {s.opposite_labels[lang]}"
            else:
                d[f"slider.{s.id}"] = s.labels[lang]
            d[f"slider.{s.id}.info"] = s.descriptions[lang]
            for stage in s.stages:
                d[f"stage.{s.id}.{stage.id}"] = stage.labels[lang]
        for g in catalog.groups.values():
            d[f"group.{g.id}"] = g.labels[lang]
        for pid, p in catalog.profiles.items():
            d[f"profile.{pid}"] = p.labels[lang]
        for c in catalog.conflicts:
            d[f"conflict.{c.a}.{c.b}"] = c.hints[lang]
        for pid, p in (library or {}).items():
            d[f"profile.library.{pid}"] = p.display_name(lang)
    return out


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class Translator:
    def __init__(self, catalogs: dict[str, dict[str, str]]) -> None:
        self.catalogs = catalogs

    def lang(self, code: str | None) -> str:
        code = (code or "").lower().replace("_", "-")
        base = code.split("-")[0]
        return base if base in self.catalogs else FALLBACK

    def t(self, key: str, lang: str | None = None, **params: object) -> str:
        lang = self.lang(lang)
        text = self.catalogs[lang].get(key) or self.catalogs[FALLBACK].get(key) or key
        if not params:
            return text
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return text

    def issue(self, issue: Issue, lang: str | None) -> str:
        # The core reports languages as codes; show their names in the interface language.
        lang = self.lang(lang)
        params: dict[str, object] = {}
        for k, v in issue.params.items():
            if k in LANGUAGE_PARAMS and isinstance(v, str):
                v = self.t(f"language.{v}", lang)
            elif k in NAMED_PARAMS and isinstance(v, str):
                v = self.t(f"{NAMED_PARAMS[k]}.{v}", lang)
            elif isinstance(v, float):
                v = number(v, lang)
            params[k] = v
        return self.t(f"issue.{issue.code}", lang, **params)

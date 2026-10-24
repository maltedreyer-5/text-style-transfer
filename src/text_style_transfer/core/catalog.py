# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Loads the packaged, read-only data: sliders, groups, conflicts, built-in
profiles and the six text-language packs.

Every inconsistency raises CatalogError at startup. Starting with a partial
catalog would silently produce prompts without the affected style features.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .indicators import IndicatorRules
from .models import (
    TEXT_LANGUAGES,
    UI_LANGUAGES,
    Conflict,
    Group,
    Pole,
    Profile,
    Slider,
    SliderType,
    Stage,
)
from .profiles import profile_from_dict

_ID = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class CatalogError(RuntimeError):
    """The packaged data is inconsistent. Message is for operators (English)."""


@dataclass(frozen=True)
class LanguagePack:
    code: str
    endonym: str
    english_name: str
    examples: dict[str, str]
    decimal_separator: str
    group_separators: tuple[str, ...]
    quotes: tuple[tuple[str, str], ...]
    preamble_patterns: tuple[re.Pattern[str], ...]
    trailer_patterns: tuple[re.Pattern[str], ...]
    function_words: frozenset[str]
    abbreviations: tuple[str, ...]
    indicators: IndicatorRules


@dataclass
class Catalog:
    sliders: dict[str, Slider]
    groups: dict[str, Group]
    conflicts: list[Conflict]
    profiles: dict[str, Profile]
    languages: dict[str, LanguagePack]
    example_keys: frozenset[str] = field(default_factory=frozenset)

    def sliders_in_group(self, group_id: str) -> list[Slider]:
        return [s for s in self.sliders.values() if s.group == group_id]


def _read_json(*parts: str) -> object:
    path = resources.files("text_style_transfer").joinpath("data", *parts)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read data/{'/'.join(parts)}: {exc}") from exc


def _ui_texts(obj: object, where: str) -> dict[str, str]:
    if not isinstance(obj, dict) or set(obj) != set(UI_LANGUAGES):
        raise CatalogError(f"{where}: needs exactly the UI languages {UI_LANGUAGES}")
    if not all(isinstance(v, str) and v.strip() for v in obj.values()):
        raise CatalogError(f"{where}: empty text")
    return dict(obj)


def _pole(obj: object, where: str) -> Pole:
    if not isinstance(obj, dict) or not obj.get("heading") or not obj.get("instruction"):
        raise CatalogError(f"{where}: heading and instruction are required")
    return Pole(obj["heading"], obj["instruction"], obj.get("markers", ""), obj.get("example_key", ""))


def _load_sliders(groups: dict[str, Group]) -> dict[str, Slider]:
    data = _read_json("sliders.json")
    if not isinstance(data, dict) or data.get("format") != "text-style-sliders" or data.get("version") != 1:
        raise CatalogError("sliders.json: wrong format or version")
    sliders: dict[str, Slider] = {}
    for raw in data.get("sliders", []):
        sid = raw.get("id", "")
        where = f"sliders.json:{sid or '?'}"
        if not _ID.match(sid) or sid in sliders:
            raise CatalogError(f"{where}: invalid or duplicate id")
        if raw.get("group") not in groups:
            raise CatalogError(f"{where}: unknown group {raw.get('group')!r}")
        try:
            stype = SliderType(raw.get("type"))
        except ValueError:
            raise CatalogError(f"{where}: unknown type") from None
        stages: tuple[Stage, ...] = ()
        positive = negative = None
        opposite: dict[str, str] = {}
        if stype is SliderType.STAGES:
            stages = tuple(
                Stage(s["id"], s["instruction"], _ui_texts(s.get("labels"), f"{where}:{s.get('id')}"))
                for s in raw.get("stages", [])
            )
            if len(stages) < 2 or len({s.id for s in stages}) != len(stages):
                raise CatalogError(f"{where}: stages need at least two unique ids")
        else:
            positive = _pole(raw.get("positive"), f"{where}:positive")
            if stype is SliderType.POLAR:
                negative = _pole(raw.get("negative"), f"{where}:negative")
                opposite = _ui_texts(raw.get("opposite_labels"), f"{where}:opposite_labels")
        sliders[sid] = Slider(
            id=sid, type=stype, group=raw["group"],
            labels=_ui_texts(raw.get("labels"), f"{where}:labels"),
            descriptions=_ui_texts(raw.get("descriptions"), f"{where}:descriptions"),
            positive=positive, negative=negative, opposite_labels=opposite, stages=stages,
        )
    if not sliders:
        raise CatalogError("sliders.json: no sliders")
    return sliders


def _compile(patterns: object, where: str) -> tuple[re.Pattern[str], ...]:
    if not isinstance(patterns, list):
        raise CatalogError(f"{where}: list expected")
    try:
        return tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    except re.error as exc:
        raise CatalogError(f"{where}: {exc}") from exc


def _load_language(code: str) -> LanguagePack:
    raw = _read_json("lang", f"{code}.json")
    where = f"lang/{code}.json"
    if not isinstance(raw, dict) or raw.get("code") != code:
        raise CatalogError(f"{where}: code mismatch")
    quotes = tuple(tuple(q) for q in raw.get("quotes", []))
    if not quotes or any(len(q) != 2 for q in quotes):
        raise CatalogError(f"{where}: quotes must be pairs")
    words = raw.get("function_words", [])
    if len(words) < 20:
        raise CatalogError(f"{where}: at least 20 function words required")
    ind = raw.get("indicators")
    if not isinstance(ind, dict) or not ind.get("personal") or not ind.get("hedges") or not ind.get("nominal_suffix"):
        raise CatalogError(f"{where}: indicators need personal, hedges and nominal_suffix")
    if not (ind.get("familiar_address") or ind.get("familiar_regex")):
        raise CatalogError(f"{where}: indicators need familiar_address or familiar_regex")
    try:
        indicators = IndicatorRules.from_data(ind)
    except re.error as exc:
        raise CatalogError(f"{where}: indicators: {exc}") from exc
    return LanguagePack(
        code=code,
        endonym=raw["endonym"],
        english_name=raw["english_name"],
        examples=dict(raw.get("examples", {})),
        decimal_separator=raw["decimal_separator"],
        group_separators=tuple(raw.get("group_separators", [])),
        quotes=quotes,  # type: ignore[arg-type]
        preamble_patterns=_compile(raw.get("preamble_patterns", []), f"{where}:preamble_patterns"),
        trailer_patterns=_compile(raw.get("trailer_patterns", []), f"{where}:trailer_patterns"),
        function_words=frozenset(w.lower() for w in words),
        abbreviations=tuple(raw.get("abbreviations", [])),
        indicators=indicators,
    )


def load_catalog() -> Catalog:
    groups_raw = _read_json("groups.json")
    groups = {g["id"]: Group(g["id"], _ui_texts(g.get("labels"), f"groups.json:{g['id']}"))
              for g in groups_raw.get("groups", [])}  # type: ignore[union-attr]
    sliders = _load_sliders(groups)

    conflicts: list[Conflict] = []
    for c in _read_json("conflicts.json").get("conflicts", []):  # type: ignore[union-attr]
        if c.get("a") not in sliders or c.get("b") not in sliders:
            raise CatalogError(f"conflicts.json: unknown slider in {c.get('a')}/{c.get('b')}")
        conflicts.append(Conflict(c["a"], c["b"], _ui_texts(c.get("hints"), f"conflicts.json:{c['a']}+{c['b']}")))

    languages = {code: _load_language(code) for code in TEXT_LANGUAGES}
    keys = {frozenset(p.examples) for p in languages.values()}
    if len(keys) != 1:
        raise CatalogError("lang/*.json: every language pack needs the same example keys")
    example_keys = next(iter(keys))
    for slider in sliders.values():
        for pole in (slider.positive, slider.negative):
            if pole and pole.example_key and pole.example_key not in example_keys:
                raise CatalogError(f"sliders.json:{slider.id}: example key {pole.example_key!r} missing in language packs")

    profiles: dict[str, Profile] = {}
    folder = resources.files("text_style_transfer").joinpath("data", "profiles")
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".json"):
            continue
        pid = entry.name[:-5]
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogError(f"profiles/{entry.name}: {exc}") from exc
        profile, issues = profile_from_dict(data, sliders)
        if issues:
            raise CatalogError(f"profiles/{entry.name}: {[i.code for i in issues]}")
        if profile.id != pid or set(profile.labels) != set(UI_LANGUAGES):
            raise CatalogError(f"profiles/{entry.name}: id must match file name, labels need {UI_LANGUAGES}")
        profile.origin = "builtin"
        profiles[pid] = profile
    return Catalog(sliders, groups, conflicts, profiles, languages, example_keys)


def load_library(folder: Path, sliders: dict[str, Slider]) -> dict[str, Profile]:
    """Profiles an operator provides in TST_PROFILE_DIR, read once at startup.

    The directory is only read, never written. Any problem stops the start,
    so that a broken file is noticed instead of silently missing.
    """
    library: dict[str, Profile] = {}
    for path in sorted(folder.glob("*.json")):
        pid = path.stem
        if not _ID.match(pid):
            raise CatalogError(f"{path}: file name must match {_ID.pattern} (it becomes the profile id)")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile, issues = profile_from_dict(data, sliders)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise CatalogError(f"{path}: {exc}") from exc
        if issues:
            raise CatalogError(f"{path}: {[i.code for i in issues]}")
        profile.id = pid
        library[pid] = profile
    return library

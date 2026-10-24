# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Profile JSON format, version 1: validation and serialization.

The format is a public interface: profiles travel as files and as profile
codes. Validation is strict about structure (an unreadable profile is
rejected) and lenient about content (unknown sliders or out-of-range values
are dropped or clamped, and every such correction is reported as an Issue,
never applied silently).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .models import (
    NEUTRALIZATION_DIMENSIONS,
    ORIGINS,
    STRENGTHS,
    TEXT_LANGUAGES,
    UI_LANGUAGES,
    CustomSlider,
    Issue,
    Neutralization,
    Profile,
    Slider,
    SliderType,
)

FORMAT_ID = "text-style-profile"
FORMAT_VERSION = 1

MAX_NAME = 80
MAX_DESCRIPTION = 2000
MAX_RULES = 12
MAX_RULE = 300
MAX_CUSTOM_SLIDERS = 5
MAX_CUSTOM_LABEL = 60
MAX_CUSTOM_TEXT = 500

METRIC_KEYS: tuple[str, ...] = (
    "sentence_length_mean",
    "sentence_length_sd",
    "sentences_per_paragraph",
    "word_length_mean",
    "mattr",
    "commas_per_sentence",
    "question_share",
    "exclamation_share",
    "dialogue_share",
    "words_measured",
    "personal_rate",
    "formal_rate",
    "familiar_rate",
    "hedge_rate",
    "nominal_rate",
    "list_share",
)

# Measured values a profile asks the model to aim for. Analysis presets them
# from the measurements; the user can change or switch off each one.
TARGET_RANGES: dict[str, tuple[float, float]] = {
    "sentence_length_mean": (3, 80),
    "sentence_length_sd": (0, 40),
    "sentences_per_paragraph": (1, 30),
    "commas_per_sentence": (0, 10),
    "question_share": (0, 1),
    "exclamation_share": (0, 1),
    "dialogue_share": (0, 1),
}

_CUSTOM_ID = re.compile(r"^custom_[a-z0-9_]{1,30}$")


class ProfileError(ValueError):
    """The data is not a readable version-1 profile."""

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def _text(value: object, limit: int, field_name: str, issues: list[Issue]) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProfileError("profile_field_type", field=field_name)
    value = value.strip()
    if len(value) > limit:
        issues.append(Issue("profile_truncated", {"field": field_name, "limit": limit}))
        value = value[:limit]
    return value


def _get(data: Mapping, key: str, default: object) -> object:
    """Missing or null means default; an empty value of the wrong type stays wrong.

    (`data.get(key) or default` would accept [] where an object is required.)
    """
    value = data.get(key)
    return default if value is None else value


def _custom_slider(raw: object, issues: list[Issue]) -> CustomSlider | None:
    if not isinstance(raw, Mapping):
        raise ProfileError("profile_field_type", field="custom_sliders")
    sid = raw.get("id")
    stype = raw.get("type")
    if not isinstance(sid, str) or not _CUSTOM_ID.match(sid):
        issues.append(Issue("custom_slider_invalid", {"id": str(sid)[:40]}))
        return None
    if stype not in (SliderType.POLAR.value, SliderType.INTENSITY.value):
        issues.append(Issue("custom_slider_invalid", {"id": sid}))
        return None
    label = _text(raw.get("label"), MAX_CUSTOM_LABEL, "custom_sliders.label", issues)
    instruction = _text(raw.get("instruction"), MAX_CUSTOM_TEXT, "custom_sliders.instruction", issues)
    if not label or not instruction:
        issues.append(Issue("custom_slider_invalid", {"id": sid}))
        return None
    return CustomSlider(
        id=sid,
        type=SliderType(stype),
        label=label,
        instruction=instruction,
        markers=_text(raw.get("markers"), MAX_CUSTOM_TEXT, "custom_sliders.markers", issues),
        opposite_label=_text(raw.get("opposite_label"), MAX_CUSTOM_LABEL, "custom_sliders.opposite_label", issues),
        opposite_instruction=_text(raw.get("opposite_instruction"), MAX_CUSTOM_TEXT, "custom_sliders.opposite_instruction", issues),
        opposite_markers=_text(raw.get("opposite_markers"), MAX_CUSTOM_TEXT, "custom_sliders.opposite_markers", issues),
    )


def profile_from_dict(data: object, sliders: Mapping[str, Slider]) -> tuple[Profile, list[Issue]]:
    """Validate a version-1 profile and return it with a list of corrections."""
    if not isinstance(data, Mapping):
        raise ProfileError("profile_not_object")
    if data.get("format") != FORMAT_ID:
        raise ProfileError("profile_wrong_format")
    if data.get("version") != FORMAT_VERSION:
        raise ProfileError("profile_wrong_version", version=str(data.get("version"))[:10])

    issues: list[Issue] = []
    name = _text(data.get("name"), MAX_NAME, "name", issues) or "Unnamed"

    language = data.get("language")
    if language is not None and language not in TEXT_LANGUAGES:
        issues.append(Issue("profile_unknown_language", {"language": str(language)[:10]}))
        language = None

    customs: list[CustomSlider] = []
    raw_customs = _get(data, "custom_sliders", [])
    if not isinstance(raw_customs, list):
        raise ProfileError("profile_field_type", field="custom_sliders")
    for raw in raw_customs[:MAX_CUSTOM_SLIDERS]:  # type: ignore[index]
        custom = _custom_slider(raw, issues)
        if custom and all(c.id != custom.id for c in customs):
            customs.append(custom)
    if len(raw_customs) > MAX_CUSTOM_SLIDERS:
        issues.append(Issue("profile_truncated", {"field": "custom_sliders", "limit": MAX_CUSTOM_SLIDERS}))

    known: dict[str, Slider] = dict(sliders)
    known.update({c.id: c.to_slider() for c in customs})

    values: dict[str, int | str] = {}
    raw_values = _get(data, "sliders", {})
    if not isinstance(raw_values, Mapping):
        raise ProfileError("profile_field_type", field="sliders")
    for sid, raw in raw_values.items():
        slider = known.get(sid)
        if slider is None:
            issues.append(Issue("unknown_slider", {"id": str(sid)[:40]}))
            continue
        value = slider.coerce(raw)
        if value is None:
            issues.append(Issue("invalid_slider_value", {"id": sid}))
            continue
        if not isinstance(raw, str) and isinstance(value, int) and value != raw:
            issues.append(Issue("slider_value_clamped", {"id": sid, "value": value}))
        values[sid] = value

    neutral = Neutralization()
    raw_neutral = data.get("neutralization")
    if raw_neutral is not None:
        if not isinstance(raw_neutral, Mapping):
            raise ProfileError("profile_field_type", field="neutralization")
        strength = raw_neutral.get("strength", "normal")
        if strength not in STRENGTHS:
            issues.append(Issue("profile_invalid_value", {"field": "neutralization.strength"}))
            strength = "normal"
        dims_raw = raw_neutral.get("dimensions", list(neutral.dimensions))
        if not isinstance(dims_raw, list):
            raise ProfileError("profile_field_type", field="neutralization.dimensions")
        dims = tuple(d for d in dims_raw if d in NEUTRALIZATION_DIMENSIONS)
        if len(dims) != len(dims_raw):
            issues.append(Issue("profile_invalid_value", {"field": "neutralization.dimensions"}))
        neutral = Neutralization(bool(raw_neutral.get("enabled", True)), strength, dims)

    rules_raw = _get(data, "rules", [])
    if not isinstance(rules_raw, list):
        raise ProfileError("profile_field_type", field="rules")
    rules = [r for r in (_text(x, MAX_RULE, "rules", issues) for x in rules_raw[:MAX_RULES]) if r]
    if len(rules_raw) > MAX_RULES:
        issues.append(Issue("profile_truncated", {"field": "rules", "limit": MAX_RULES}))

    metrics: dict[str, float] = {}
    raw_metrics = _get(data, "metrics", {})
    if not isinstance(raw_metrics, Mapping):
        raise ProfileError("profile_field_type", field="metrics")
    for key, raw in raw_metrics.items():
        if key in METRIC_KEYS and isinstance(raw, (int, float)) and not isinstance(raw, bool):
            metrics[key] = float(raw)
        else:
            issues.append(Issue("profile_invalid_value", {"field": f"metrics.{str(key)[:30]}"}))

    targets: dict[str, float] = {}
    raw_targets = _get(data, "targets", None)
    if raw_targets is None:
        # A profile without explicit targets aims at what was measured.
        raw_targets = {k: v for k, v in metrics.items() if k in TARGET_RANGES}
    if not isinstance(raw_targets, Mapping):
        raise ProfileError("profile_field_type", field="targets")
    for key, raw in raw_targets.items():
        if key not in TARGET_RANGES or not isinstance(raw, (int, float)) or isinstance(raw, bool):
            issues.append(Issue("profile_invalid_value", {"field": f"targets.{str(key)[:30]}"}))
            continue
        low, high = TARGET_RANGES[key]
        value = min(high, max(low, float(raw)))
        if value != raw:
            issues.append(Issue("profile_invalid_value", {"field": f"targets.{key}"}))
        targets[key] = value

    origin = data.get("origin", "manual")
    if origin not in ORIGINS:
        origin = "manual"

    labels_raw = _get(data, "labels", {})
    labels = {k: v.strip()[:MAX_NAME] for k, v in labels_raw.items()
              if k in UI_LANGUAGES and isinstance(v, str) and v.strip()} if isinstance(labels_raw, Mapping) else {}

    desc_raw = _get(data, "descriptions", {})
    descriptions = {k: v.strip()[:MAX_DESCRIPTION] for k, v in desc_raw.items()
                    if k in UI_LANGUAGES and isinstance(v, str) and v.strip()} if isinstance(desc_raw, Mapping) else {}

    pid = data.get("id")
    profile = Profile(
        name=name,
        language=language,
        sliders=values,
        neutralization=neutral,
        description=_text(data.get("description"), MAX_DESCRIPTION, "description", issues),
        rules=rules,
        metrics=metrics,
        custom_sliders=customs,
        origin=origin,
        labels=labels,
        descriptions=descriptions,
        targets=targets,
        id=pid if isinstance(pid, str) else None,
    )
    return profile, issues


def profile_to_dict(profile: Profile) -> dict:
    """Serialize a profile; keys are stable and sorted for reproducible codes."""
    data: dict[str, object] = {
        "format": FORMAT_ID,
        "version": FORMAT_VERSION,
        "name": profile.name,
        "language": profile.language,
        "sliders": dict(sorted(profile.sliders.items())),
        "neutralization": {
            "enabled": profile.neutralization.enabled,
            "strength": profile.neutralization.strength,
            "dimensions": list(profile.neutralization.dimensions),
        },
        "origin": profile.origin,
    }
    if profile.description:
        data["description"] = profile.description
    if profile.rules:
        data["rules"] = list(profile.rules)
    if profile.metrics:
        data["metrics"] = {k: round(v, 3) for k, v in sorted(profile.metrics.items())}
    if profile.targets:
        data["targets"] = {k: round(v, 3) for k, v in sorted(profile.targets.items())}
    if profile.custom_sliders:
        data["custom_sliders"] = [
            {k: v for k, v in {
                "id": c.id, "type": c.type.value, "label": c.label,
                "instruction": c.instruction, "markers": c.markers,
                "opposite_label": c.opposite_label,
                "opposite_instruction": c.opposite_instruction,
                "opposite_markers": c.opposite_markers,
            }.items() if v}
            for c in profile.custom_sliders
        ]
    if profile.labels:
        data["labels"] = dict(sorted(profile.labels.items()))
    if profile.descriptions:
        data["descriptions"] = dict(sorted(profile.descriptions.items()))
    if profile.id:
        data["id"] = profile.id
    return data

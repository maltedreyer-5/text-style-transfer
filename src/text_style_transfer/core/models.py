# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Data model shared by the core: sliders, profiles, neutralization settings.

Invariant: no text shown to users is ever used as a key, a comparison value
or prompt content. Every slider, stage and profile has a stable English id;
display labels and prompt texts live in separate fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

TEXT_LANGUAGES: tuple[str, ...] = ("en", "de", "fr", "es", "it", "pl")
UI_LANGUAGES: tuple[str, ...] = ("en", "de")

NEUTRALIZATION_DIMENSIONS: tuple[str, ...] = (
    "tone",
    "register",
    "word_choice",
    "redundancy",
    "subjectivity",
    "perspective",
    "intensifiers",
    "structure",
    "figurative",
    "cultural_references",
)
DEFAULT_DIMENSIONS: tuple[str, ...] = ("tone", "register", "redundancy")
STRENGTHS: tuple[str, ...] = ("gentle", "normal", "thorough")

ORIGINS: tuple[str, ...] = ("builtin", "analysis", "description", "manual", "refined")


class SliderType(StrEnum):
    POLAR = "polar"            # -10 .. +10, 0 = inactive
    INTENSITY = "intensity"    # 1 .. 10
    STAGES = "stages"          # one of a fixed set of stage ids


@dataclass(frozen=True)
class Pole:
    """One direction of a slider."""

    heading: str               # English, used only inside prompts
    instruction: str           # English, valid for every text language
    markers: str = ""          # English, language-neutral recognition hints
    example_key: str = ""      # key into the language pack's "examples"


@dataclass(frozen=True)
class Stage:
    id: str
    instruction: str           # English
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Slider:
    id: str
    type: SliderType
    group: str
    labels: dict[str, str]
    descriptions: dict[str, str]
    positive: Pole | None = None
    negative: Pole | None = None          # polar sliders only
    opposite_labels: dict[str, str] = field(default_factory=dict)
    stages: tuple[Stage, ...] = ()
    custom: bool = False

    def stage(self, stage_id: str) -> Stage | None:
        return next((s for s in self.stages if s.id == stage_id), None)

    def coerce(self, value: object) -> int | str | None:
        """Return a valid, active value or None.

        Gradio sliders deliver floats and stored data may carry strings, so
        every value passes through here before it reaches a prompt.
        """
        if self.type is SliderType.STAGES:
            if isinstance(value, str) and self.stage(value) is not None:
                return value
            return None
        if isinstance(value, bool):
            return None
        try:
            number = int(round(float(value)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if self.type is SliderType.POLAR:
            number = max(-10, min(10, number))
            return number or None
        number = max(0, min(10, number))
        return number or None


@dataclass(frozen=True)
class Group:
    id: str
    labels: dict[str, str]


@dataclass(frozen=True)
class Conflict:
    a: str
    b: str
    hints: dict[str, str]


@dataclass
class Neutralization:
    enabled: bool = True
    strength: str = "normal"
    dimensions: tuple[str, ...] = DEFAULT_DIMENSIONS

    def key(self) -> str:
        return f"{self.strength}|{','.join(sorted(self.dimensions))}"


@dataclass
class CustomSlider:
    """A user-defined slider that travels inside a personal profile."""

    id: str
    type: SliderType            # POLAR or INTENSITY
    label: str
    instruction: str
    markers: str = ""
    opposite_label: str = ""
    opposite_instruction: str = ""
    opposite_markers: str = ""

    def to_slider(self) -> Slider:
        positive = Pole(self.label.upper(), self.instruction, self.markers)
        negative = None
        if self.type is SliderType.POLAR:
            negative = Pole(
                (self.opposite_label or self.label).upper(),
                self.opposite_instruction,
                self.opposite_markers,
            )
        labels = {lang: self.label for lang in UI_LANGUAGES}
        opposite = {lang: self.opposite_label for lang in UI_LANGUAGES}
        return Slider(
            id=self.id, type=self.type, group="custom", labels=labels,
            descriptions={}, positive=positive, negative=negative,
            opposite_labels=opposite, custom=True,
        )


@dataclass
class Profile:
    name: str
    language: str | None = None
    sliders: dict[str, int | str] = field(default_factory=dict)
    neutralization: Neutralization = field(default_factory=Neutralization)
    description: str = ""
    rules: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    custom_sliders: list[CustomSlider] = field(default_factory=list)
    origin: str = "manual"
    labels: dict[str, str] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)
    targets: dict[str, float] = field(default_factory=dict)
    id: str | None = None

    def description_for(self, ui_lang: str) -> str:
        """Packaged profiles describe themselves in every UI language;
        profiles made by users carry one description in the language of
        the person who made them."""
        return self.descriptions.get(ui_lang) or self.description or self.descriptions.get("en", "")

    def display_name(self, ui_lang: str) -> str:
        return self.labels.get(ui_lang) or self.labels.get("en") or self.name


def has_style(profile: Profile) -> bool:
    """Does the profile ask for any target style at all?"""
    return bool(profile.sliders or profile.description.strip() or profile.rules or profile.targets)


@dataclass(frozen=True)
class Issue:
    """A message for the user, expressed as a catalog key plus parameters.

    The core never produces user-facing text; the UI translates issues.
    """

    code: str
    params: dict[str, object] = field(default_factory=dict)

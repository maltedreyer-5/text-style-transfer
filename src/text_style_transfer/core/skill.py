# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Export a profile as an Agent Skill.

A skill is a folder with a SKILL.md file: YAML front matter with `name` and
`description`, followed by Markdown instructions. The rules enforced here
follow the published format: `name` at most 64 characters of lowercase
letters, digits and single hyphens, without the reserved words "anthropic"
and "claude"; `description` non-empty, at most 1024 characters, no angle
brackets; the instructions should stay below about 5,000 tokens.

The skill carries the instructions of the profile, not the application:
the two paths become a procedure the model follows, and the checks of the
application do not run where the skill is used. The profile itself is
included as profile.json so that it can be loaded into the application
again. Reference texts are never part of a profile and so never part of a
skill.
"""

from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import __version__
from . import prompts
from .catalog import Catalog
from .metrics import metrics_to_targets
from .models import Issue, Profile, SliderType, has_style
from .profiles import profile_to_dict
from .tokens import estimate_tokens

NAME_MAX = 64
DESCRIPTION_MAX = 1024
BODY_TOKENS_RECOMMENDED = 5000
RESERVED_WORDS = ("anthropic", "claude")
NAME_PREFIX = "writing-style"
_NAME_RULE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TRANSLITERATE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "ø": "o", "ł": "l", "đ": "d",
                  "þ": "th", "œ": "oe"}


class SkillError(ValueError):
    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass
class SkillExport:
    name: str
    files: dict[str, str]
    issues: list[Issue] = field(default_factory=list)


def skill_name(profile_name: str) -> str:
    """A valid skill name derived from the profile name, e.g. writing-style-mein-stil."""
    text = "".join(_TRANSLITERATE.get(ch, ch) for ch in (profile_name or "").lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in RESERVED_WORDS]
    words = [w for w in words if not any(r in w for r in RESERVED_WORDS)]
    name = NAME_PREFIX
    for word in words:
        candidate = f"{name}-{word}"
        if len(candidate) > NAME_MAX:
            break
        name = candidate
    return name


def _plain(text: str) -> str:
    """Remove what the front matter must not contain and collapse white space."""
    return " ".join(text.replace("<", "").replace(">", "").split())


def _summary(profile: Profile, catalog: Catalog) -> str:
    headings = []
    for slider, value in prompts.active_features(profile, catalog.sliders)[:4]:
        if slider.type is SliderType.STAGES:
            headings.append(f"{slider.id.replace('_', ' ')} {value}")
        elif isinstance(value, int):
            pole = slider.positive if value > 0 else slider.negative
            if pole:
                headings.append(pole.heading.lower())
    return ", ".join(headings)


def build_description(profile: Profile, catalog: Catalog, display: str) -> str:
    language = catalog.languages.get(profile.language or "")
    scope = f" for texts in {language.english_name}" if language else ""
    summary = _summary(profile, catalog)
    what = f'Writes and rewrites text in the writing style "{display}"{scope}'
    if summary:
        what += f" ({summary})"
    when = (f'Use when the user asks to write, rewrite, edit or restyle a text in this style, '
            f'or mentions "{display}".')
    text = _plain(f"{what}. {when}")
    if len(text) > DESCRIPTION_MAX:
        text = text[:DESCRIPTION_MAX - 1].rsplit(" ", 1)[0] + "…"
    return text


def _language_hints(profile: Profile, catalog: Catalog) -> list[str]:
    poles = []
    for slider, value in prompts.active_features(profile, catalog.sliders):
        if isinstance(value, int) and slider.type is not SliderType.STAGES:
            pole = slider.positive if value > 0 else slider.negative
            if pole and pole.example_key:
                poles.append(pole)
    if not poles:
        return []
    codes = [profile.language] if profile.language else list(catalog.languages)
    lines = ["## Language-specific hints", ""]
    for code in codes:
        pack = catalog.languages[code]
        lines.append(f"### {pack.english_name} ({pack.endonym})")
        lines += [f"- **{p.heading}:** {pack.examples[p.example_key]}" for p in poles]
        lines.append("")
    return lines


def build_skill_md(profile: Profile, catalog: Catalog, name: str, description: str, display: str) -> str:
    language = catalog.languages.get(profile.language or "")
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(description, ensure_ascii=False)}",  # a JSON string is valid YAML
        "---",
        "",
        f"# Writing style: {_plain(display)}",
        "",
        "Apply this style when you write new text or rewrite a text for the user.",
        "",
        "## Procedure",
        "",
        "1. Keep the language of the text you rewrite, or the language the user writes in. Do not "
        "translate." + (f" This style was made for texts in {language.english_name}; in other "
                        "languages, apply the features as far as they carry over." if language else ""),
    ]
    neutral = profile.neutralization
    if neutral.enabled and neutral.dimensions:
        dims = "\n".join("   - " + prompts.NEUTRALIZATION_TEXT[d].replace(" (for example {example})", "")
                         for d in neutral.dimensions if d in prompts.NEUTRALIZATION_TEXT)
        lines.append("2. If the source text has a strong style of its own, first neutralise it in a "
                     "working draft (do not show the draft unless asked). Depth: "
                     + prompts.STRENGTH_TEXT.get(neutral.strength, prompts.STRENGTH_TEXT["normal"]) + "\n" + dims)
    else:
        lines.append("2. Work on the source text as it is.")
    lines += [
        "3. Apply the style features below, in the order given; a feature listed earlier wins a conflict.",
        "4. Check the result against the invariable rules and the final check.",
        "5. Give the result without preamble or commentary, unless the user asks for explanations.",
        "",
    ]

    features = prompts.feature_lines(profile, catalog.sliders, None)
    if features:
        lines += ["## Style features", "", "```text", *features, "```", ""]
    lines += _language_hints(profile, catalog)
    description_text = profile.description.strip()
    if description_text:
        lines += ["## Style description", "", description_text, ""]
    if profile.rules:
        lines += ["## Additional rules", "", *[f"- {r}" for r in profile.rules], ""]
    targets = metrics_to_targets(profile.targets)
    if targets:
        words = int(profile.metrics.get("words_measured", 0))
        origin = (f"Measured on about {words} words of reference text, possibly adjusted by hand; "
                  if words else "Set by hand; ")
        lines += ["## Measured targets", "", origin + "approximate values.", "", *[f"- {t}" for t in targets], ""]

    length = profile.sliders.get("length")
    if isinstance(length, int):
        share = round(prompts.length_factor(length) * 100)
        length_rule = f"When rewriting, make the result about {share} % as long as the source text."
    else:
        length_rule = "When rewriting, keep roughly the length of the source text (up to 20 % deviation)."
    lines += ["## Length", "", length_rule, "When writing new text, follow the length the user asks for.", ""]
    lines += [
        "## Invariable rules",
        "",
        "These take precedence over every style feature. When writing new text, they apply to the "
        "facts the user has given.",
        "",
        prompts.fact_rules(None),
        "- Mood and effect come from word choice, sentence structure and rhythm, not from invented "
        "events, evaluations or details",
        "",
        "## Final check",
        "",
        prompts.FINAL_CHECK,
        "",
        "## About this skill",
        "",
        f"Generated by Text Style Transfer {__version__}. The file `profile.json` contains the settings "
        "it was made from; load it into the application (Profile tab, JSON upload) to adjust them and "
        "export the skill again.",
        "",
    ]
    return "\n".join(lines)


def validate(name: str, description: str) -> None:
    if len(name) > NAME_MAX or not _NAME_RULE.match(name) or any(r in name for r in RESERVED_WORDS):
        raise SkillError("skill_invalid", field="name")
    if not description.strip() or len(description) > DESCRIPTION_MAX or "<" in description or ">" in description:
        raise SkillError("skill_invalid", field="description")


def build_skill(profile: Profile, catalog: Catalog, display_name: str | None = None) -> SkillExport:
    """Return the files of the skill, keyed by their path inside the archive."""
    if not has_style(profile):
        raise SkillError("skill_no_style")
    # Leading emoji or symbols of packaged profile names are decoration, not part of the name.
    display = re.sub(r"^[^\w(]+", "", _plain(display_name or profile.name)) or "Own style"
    name = skill_name(display)
    description = build_description(profile, catalog, display)
    validate(name, description)
    skill_md = build_skill_md(profile, catalog, name, description, display)
    issues = []
    body_tokens = estimate_tokens(skill_md.split("---", 2)[2])
    if body_tokens > BODY_TOKENS_RECOMMENDED:
        issues.append(Issue("skill_long", {"tokens": body_tokens, "limit": BODY_TOKENS_RECOMMENDED}))
    profile_json = json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2) + "\n"
    return SkillExport(name, {f"{name}/SKILL.md": skill_md, f"{name}/profile.json": profile_json}, issues)


def write_zip(export: SkillExport, folder: Path) -> Path:
    """Write the skill as <name>.zip with one top-level folder <name>/, as claude.ai expects."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{export.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in export.files.items():
            archive.writestr(path, content)
    return target

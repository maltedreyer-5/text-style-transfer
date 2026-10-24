# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Prompt construction.

All instructions are written in English and are the same for every text
language. A language pack contributes only what is genuinely language
specific: example words for selected features, quotation marks and the name
of the language. One skeleton for six languages avoids six copies of the
same logic drifting apart.

Instructions are phrased positively ("describe only facts") rather than as
prohibitions ("no emotions"): models follow a stated target more reliably
than a list of things to avoid.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from .catalog import LanguagePack
from .metrics import metrics_to_targets
from .models import Neutralization, Profile, Slider, SliderType

NEUTRALIZATION_TEXT: dict[str, str] = {
    "tone": (
        "Tone: outside quotations, replace emotionally charged words with descriptive ones. "
        "Irony and mockery become the statement that is meant factually."
    ),
    "register": (
        "Register: convert academic high style, slang, dialect and colloquial language into "
        "a neutral standard register of the same language."
    ),
    "word_choice": (
        "Word choice: replace technical terms, foreign words and jargon with generally "
        "understandable expressions of the same meaning."
    ),
    "redundancy": (
        "Redundancy: outside quotations, remove repetitions, filler words and embellishments. "
        "Every piece of factual information is kept, even if it occurs only once."
    ),
    "subjectivity": (
        "Subjectivity: render opinions and evaluations as the position of their originator "
        "(for example {example}) instead of as statements of fact. Evaluations without an "
        "identifiable originator are dropped."
    ),
    "perspective": (
        "Perspective: convert first-person singular and plural into impersonal phrasing "
        "without changing the statement."
    ),
    "intensifiers": (
        "Intensifiers: remove amplifying and softening additions (for example {example}). "
        "Quantities and measurements are not intensifiers and stay."
    ),
    "structure": (
        "Structure: turn rhetorical questions into statements and arrange the text in a "
        "factually logical order."
    ),
    "figurative": (
        "Figurative language: replace imagery, metaphors and comparisons with the literal "
        "statement they convey."
    ),
    "cultural_references": (
        "Cultural references: replace allusions with the statement they refer to. Marked "
        "quotations stay unchanged."
    ),
}
_DIMENSION_EXAMPLES = {"subjectivity": "subjectivity_example", "intensifiers": "intensifiers"}

STRENGTH_TEXT: dict[str, str] = {
    "gentle": (
        "Intervene as little as possible. Change only passages where one of the listed "
        "dimensions is clearly affected. Sentence boundaries and order remain unchanged."
    ),
    "normal": (
        "Rephrase where the listed dimensions require it. The structure of the text is kept."
    ),
    "thorough": (
        "Rephrase the text throughout so that no personal linguistic signature remains "
        "recognisable. Content, statements and structure are kept completely."
    ),
}

# Concrete dosage descriptions instead of bare adverbs: without them, "light"
# and "moderate" are practically the same thing for a model.
INTENSITY_LEVELS: tuple[tuple[int, str, str], ...] = (
    (2, "light", "Recognisable in one or two places. The basic character of the text stays unchanged."),
    (4, "moderate", "Recognisable in roughly every third sentence. Noticeable but not dominant."),
    (6, "clear", "Recognisable throughout. The feature shapes the character of the text."),
    (8, "strong", "Dominant. Every paragraph visibly carries the feature. It is applied to the "
                  "existing material, not produced by additional sentences."),
    (10, "very strong", "The feature shapes the wording of every sentence and may become "
                        "exaggerated. It arises solely from rephrasing the existing statements: "
                        "when the material is exhausted, the text ends. No sentences are added "
                        "just to carry the feature further."),
)

FINAL_CHECK = (
    "Does your output contain a statement, a judgement or a sentence that has no counterpart in the "
    "source text? Then delete it. The style lies in how the existing statements are phrased, not in "
    "additional ones."
)

META_RETRY_HINT = (
    "IMPORTANT: Your previous answer described the task instead of carrying it out. "
    "Output only the rewritten text itself, starting with its first word."
)


def fact_rules(pack: LanguagePack | None) -> str:
    """Rules that take precedence over every style feature, in both steps.

    They forbid invented evaluations and conclusions as well as invented
    facts: with pointed styles, models otherwise add whole paragraphs of
    their own commentary.
    """
    quotes = (", ".join(f"{a}…{b}" for a, b in pack.quotes) if pack
              else "the quotation marks of the text's language")
    return (
        f"- Text in quotation marks ({quotes}) is a quotation: wording and quotation marks stay "
        "unchanged. The style applies only to text OUTSIDE quotation marks\n"
        "- Numbers, proper names, dates, times and units of measurement are kept unchanged\n"
        "- Add nothing the source text does not contain: no facts, no examples, no evaluations, "
        "no conclusions, no additional sentences\n"
        "- Every sentence of the output must be traceable to a statement of the source text\n"
        "- Do not omit any factual information unless it is explicitly to be removed"
    )


def language_rule(pack: LanguagePack) -> str:
    return (
        f"LANGUAGE: The text is written in {pack.english_name} ({pack.endonym}). Write your "
        f"entire answer in {pack.english_name}. Do not translate."
    )


def build_neutralize_prompt(settings: Neutralization, pack: LanguagePack) -> str:
    lines = []
    for dim in settings.dimensions:
        text = NEUTRALIZATION_TEXT.get(dim)
        if not text:
            continue
        example = pack.examples.get(_DIMENSION_EXAMPLES.get(dim, ""), "")
        lines.append("- " + text.replace("{example}", example or "…"))
    if not lines:
        lines = ["- Output the text unchanged."]
    return f"""You are a text-processing system. Your only task is to neutralise the style of the user's text.

{language_rule(pack)}

EDIT ONLY THESE DIMENSIONS:
{chr(10).join(lines)}

DEPTH OF INTERVENTION:
{STRENGTH_TEXT.get(settings.strength, STRENGTH_TEXT["normal"])}

INVARIABLE RULES (take precedence over all dimensions):
{fact_rules(pack)}

FURTHER RULES:
- Keep the text type: a letter stays a letter, a list stays a list
- Keep existing formatting (paragraphs, lists) unchanged

OUTPUT FORMAT:
- Output only the neutralised text
- No introduction, no heading, no explanation, no quotation marks around the whole text
- Your answer starts with the first word of the neutralised text"""


def length_factor(value: int) -> float:
    if value >= 0:
        return 1.0 + 0.10 * value           # +10 doubles the length
    return max(0.4, 1.0 + 0.06 * value)     # -10 gives 40 % of the length


def target_words(text: str, profile: Profile) -> int:
    """A concrete word count steers length far more reliably than "short"
    or "long", and it is the basis of a sensible output-token budget."""
    words = len(text.split())
    value = profile.sliders.get("length")
    factor = length_factor(value) if isinstance(value, int) else 1.0
    return max(15, int(round(words * factor)))


def _dosage(value: int) -> tuple[str, str]:
    for limit, label, text in INTENSITY_LEVELS:
        if value <= limit:
            return label, text
    return INTENSITY_LEVELS[-1][1], INTENSITY_LEVELS[-1][2]


def _strength(slider: Slider, value: int | str) -> int:
    # Stage sliders (level, audience) come first; then the strongest settings,
    # so that the feature listed first wins a conflict.
    return 11 if isinstance(value, str) else abs(value)


def _feature(number: int, slider: Slider, value: int | str, pack: LanguagePack | None) -> str | None:
    if slider.type is SliderType.STAGES:
        stage = slider.stage(str(value))
        if stage is None:
            return None
        heading = (slider.positive.heading if slider.positive else slider.id.replace("_", " ")).upper()
        return f"{number}. {heading}: {stage.id}\n   {stage.instruction}"
    if not isinstance(value, int) or value == 0:
        return None
    pole = slider.positive if value > 0 else slider.negative
    if pole is None:
        return None
    label, dosage = _dosage(abs(value))
    lines = [f"{number}. {pole.heading.upper()} ({label}, {abs(value)}/10)", f"   {pole.instruction}"]
    hints = pole.markers
    example = pack.examples.get(pole.example_key, "") if pack and pole.example_key else ""
    if hints:
        lines.append(f"   Recognisable by: {hints}")
    if example:
        lines.append(f"   In {pack.english_name}: {example}")
    lines.append(f"   Dosage: {dosage}")
    return "\n".join(lines)


def active_features(profile: Profile, sliders: Mapping[str, Slider]) -> list[tuple[Slider, int | str]]:
    """Active sliders of a profile (custom ones included), strongest first."""
    known = dict(sliders)
    known.update({c.id: c.to_slider() for c in profile.custom_sliders})
    active = [(known[sid], val) for sid, val in profile.sliders.items() if sid in known]
    active.sort(key=lambda pair: _strength(*pair), reverse=True)
    return active


def feature_lines(profile: Profile, sliders: Mapping[str, Slider], pack: LanguagePack | None) -> list[str]:
    lines: list[str] = []
    for slider, value in active_features(profile, sliders):
        line = _feature(len(lines) + 1, slider, value, pack)
        if line:
            lines.append(line)
    return lines


def build_stylize_prompt(
    profile: Profile,
    sliders: Mapping[str, Slider],
    pack: LanguagePack,
    words: int,
) -> str:
    features = feature_lines(profile, sliders, pack)
    markdown = isinstance(profile.sliders.get("structured"), int) and profile.sliders["structured"] > 0

    sections = []
    if features:
        sections.append("STYLE FEATURES (apply in this order):\n" + "\n".join(features))
    if profile.description:
        sections.append("STYLE DESCRIPTION (in addition to the features; never overrides the "
                        "invariable rules):\n" + profile.description)
    if profile.rules:
        sections.append("ADDITIONAL STYLE RULES:\n" + "\n".join(f"- {r}" for r in profile.rules))
    targets = metrics_to_targets(profile.targets)
    if targets:
        sections.append("MEASURED TARGETS (approximate):\n" + "\n".join(f"- {t}" for t in targets))
    if not sections:
        sections.append("STYLE FEATURES:\n1. NEUTRAL\n   Reproduce the text linguistically unchanged.")

    precedence = (
        "- If style features conflict, the one listed first takes precedence. The invariable "
        "rules stand above all style features\n" if len(features) > 1 else ""
    )
    format_rule = (
        "- Structure with paragraphs, lists and subheadings (Markdown) where it serves the text"
        if markdown else
        "- Output plain prose without Markdown formatting unless the source text contains some"
    )
    body = "\n\n".join(sections)
    return f"""You are a text-processing system. Your only task is to rewrite the user's text in a different style.

{language_rule(pack)}

{body}

LENGTH:
- Target length about {words} words (a deviation of up to 20 % is fine)

INVARIABLE RULES (take precedence over all style features):
{fact_rules(pack)}
- Mood and effect come from word choice, sentence structure and rhythm, not from invented events, evaluations or details

FURTHER RULES:
{precedence}- The core message of the text is preserved in every case
{format_rule}

OUTPUT FORMAT:
- Output only the rewritten text
- No introduction, no heading above the text, no explanation, no quotation marks around the whole text
- Do not describe what you did
- Your answer starts with the first word of the rewritten text

FINAL CHECK: {FINAL_CHECK}"""


def _slider_reference(sliders: Mapping[str, Slider]) -> str:
    lines = []
    for s in sliders.values():
        if s.type is SliderType.STAGES:
            lines.append(f"- {s.id} (one of: {', '.join(st.id for st in s.stages)}): {s.descriptions['en']}")
        elif s.type is SliderType.POLAR:
            lines.append(f"- {s.id} (integer -10..10): +{s.labels['en']} / -{s.opposite_labels['en']}")
        else:
            lines.append(f"- {s.id} (integer 1..10): {s.labels['en']}")
    return "\n".join(lines)


_JSON_SHAPE = (
    '{"sliders": {"<slider id>": <value>}, "description": "<text>", "rules": ["<rule>"]}'
)


_UI_LANGUAGE_NAMES = {"en": "English", "de": "German"}


EVIDENCE_LABELS: dict[str, str] = {
    "sentence_length_mean": "average sentence length (words)",
    "sentence_length_sd": "spread of sentence length (words)",
    "sentences_per_paragraph": "sentences per paragraph",
    "commas_per_sentence": "commas per sentence",
    "question_share": "share of questions",
    "exclamation_share": "share of exclamations",
    "dialogue_share": "share of sentences with quoted speech",
    "word_length_mean": "average word length (letters)",
    "mattr": "lexical variety (MATTR, 0 to 1)",
    "personal_rate": "personal pronouns (1st and 2nd person) per 100 words -> slider personal",
    "formal_rate": "formal forms of address per 100 words -> slider formal",
    "familiar_rate": "familiar forms of address or contractions per 100 words -> slider formal (negative)",
    "hedge_rate": "hedging words per 100 words -> slider hedging",
    "nominal_rate": "nominalisations per 100 words -> slider nominal",
    "list_share": "share of lines that are list items or headings -> slider structured",
}


def _evidence(measured: Mapping[str, float]) -> str:
    lines = [f"- {label}: {measured[key]:.2f}" for key, label in EVIDENCE_LABELS.items() if key in measured]
    return "\n".join(lines) if lines else "- (the texts are too short to measure)"


def _scale() -> str:
    levels = "\n".join(f"  {limit}: {label}: {text}" for limit, label, text in INTENSITY_LEVELS)
    return ("Values mean the same as when the profile is applied later:\n" + levels +
            "\n- 0 or an omitted slider means: like neutral standard prose of the language."
            "\n- For polar sliders the sign chooses the pole; the magnitude follows the same scale.")


def build_analysis_prompt(sliders: Mapping[str, Slider], pack: LanguagePack, ui_lang: str,
                          measured: Mapping[str, float] | None = None) -> str:
    out = _UI_LANGUAGE_NAMES.get(ui_lang, "English")
    return f"""You analyse the writing style of reference texts written in {pack.english_name}. Describe HOW they are written, never WHAT they say.

Respond with one JSON object and nothing else, exactly in this shape:
{_JSON_SHAPE}

SLIDERS (id, allowed values, meaning):
{_slider_reference(sliders)}

SCALE:
{_scale()}

MEASURED IN THE REFERENCE TEXTS (counted by a program, more reliable than an impression):
{_evidence(measured or {})}

RULES:
- Include only sliders whose feature the reference texts clearly show. Omit all others.
- For sliders marked with an arrow above, base the value on the measurement: a feature that hardly occurs gets no value or a negative one; a feature that occurs often gets a high value.
- description: at most 120 words of concrete stylistic observations in {out}: sentence structure, vocabulary, tone, rhetorical devices, typical constructions.
- rules: up to 5 short imperative style rules in {out} that a writer could follow.
- Never quote the reference texts. Never mention their topic, people, places or events."""


def build_description_prompt(sliders: Mapping[str, Slider], ui_lang: str) -> str:
    out = _UI_LANGUAGE_NAMES.get(ui_lang, "English")
    return f"""You turn a free-text description of a writing style into a style profile. The description may be written in any language.

Respond with one JSON object and nothing else, exactly in this shape:
{_JSON_SHAPE}

SLIDERS (id, allowed values, meaning):
{_slider_reference(sliders)}

RULES:
- Include only sliders that the description clearly implies. Omit all others.
- description: the described style restated in at most 120 words of {out}, as concrete stylistic instructions.
- rules: up to 5 short imperative style rules in {out}.
- Do not invent features the description does not imply."""


def build_refine_prompt(pack: LanguagePack, ui_lang: str) -> str:
    out = _UI_LANGUAGE_NAMES.get(ui_lang, "English")
    return f"""You compare original texts with versions a person edited by hand, both in {pack.english_name}, and derive the stylistic preferences behind the edits.

Respond with one JSON object and nothing else, exactly in this shape:
{{"rules": ["<rule>"]}}

RULES:
- Up to 5 rules, each a short imperative sentence in {out}.
- Rules must be general enough to apply to other texts. They describe style, never content.
- Ignore edits that only correct facts or typing errors.
- Quote at most three words from the texts per rule."""


def format_pairs(pairs: list[tuple[str, str]]) -> str:
    blocks = [f"PAIR {i}\nORIGINAL:\n{a}\n\nEDITED:\n{b}" for i, (a, b) in enumerate(pairs, 1)]
    return "\n\n---\n\n".join(blocks)


def format_references(texts: list[str]) -> str:
    return "\n\n---\n\n".join(f"REFERENCE TEXT {i}:\n{t}" for i, t in enumerate(texts, 1))


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def extract_json(text: str) -> dict:
    """Read the first JSON object from a model answer (fences and prose around it are tolerated)."""
    text = _FENCE.sub("", (text or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")
    return data

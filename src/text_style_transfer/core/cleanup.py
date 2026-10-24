# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Mechanical cleanup of model output.

The prompts forbid preambles, code fences and meta comments, but that is a
request, not a guarantee: smaller local models do not follow it reliably.
Every answer is therefore cleaned before it is shown or processed further.

Reasoning is never requested, but models that reason by default may still
emit it inside the content. It is removed here; the separate reasoning
fields some servers return are not read at all.
"""

from __future__ import annotations

import re

from .catalog import LanguagePack

_TAGS = "think|thinking|reasoning|scratchpad"
_REASONING_BLOCK = re.compile(rf"<({_TAGS})>.*?</\1>", re.IGNORECASE | re.DOTALL)
_CLOSING_TAG = re.compile(rf"</(?:{_TAGS})>", re.IGNORECASE)
_OPENING_TAG = re.compile(rf"^\s*<(?:{_TAGS})>", re.IGNORECASE)

# Deliberately narrow: better to leave a preamble in place than to cut off
# a genuine first line of the text.
_UNIVERSAL_PREAMBLES = [
    re.compile(p, re.IGNORECASE) for p in (
        r"^(here('s| is| are)|sure|certainly|of course)\b.{0,80}:\s*$",
        r"^(output|result|answer|text|rewritten text|neutral(ised|ized) text)\s*:\s*$",
        r"^\*{0,2}(neutrali[sz]ation|transformation|rewrite)\*{0,2}\s*:?\s*$",
    )
]
_UNIVERSAL_TRAILERS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"^\**(note|explanation)\**\s*:.*$",
        r"^i (have|'ve) (rewritten|adapted|changed|neutrali[sz]ed)\b.{0,200}$",
    )
]
_GENERIC_QUOTES = (('"', '"'), ("'", "'"), ("“", "”"), ("„", "“"), ("»", "«"), ("«", "»"))


def strip_reasoning(text: str) -> str:
    """Remove reasoning blocks. Returns "" if the answer is only reasoning."""
    text = _REASONING_BLOCK.sub("", text or "")
    closing = list(_CLOSING_TAG.finditer(text))
    if closing:
        # Some chat templates open the block implicitly and only the closing
        # tag reaches the client: everything before it is reasoning.
        text = text[closing[-1].end():]
    if _OPENING_TAG.match(text):
        return ""  # opened but never closed: the model ran out of budget while reasoning
    return text


def _strip_fence(text: str) -> str:
    lines = text.strip().split("\n")
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _strip_enclosing_quotes(text: str, pack: LanguagePack) -> str:
    text = text.strip()
    for opening, closing in tuple(pack.quotes) + _GENERIC_QUOTES:
        if len(text) > 2 and text.startswith(opening) and text.endswith(closing):
            inner = text[len(opening):-len(closing)]
            # Only if the same mark does not occur inside: otherwise these are
            # two genuine quotations at the edges of the text.
            if closing not in inner and opening not in inner:
                return inner.strip()
    return text


def _matches(line: str, patterns: list[re.Pattern[str]] | tuple[re.Pattern[str], ...]) -> bool:
    return any(p.match(line) for p in patterns)


def clean_output(text: str | None, pack: LanguagePack) -> str:
    text = strip_reasoning(text or "").replace("\r\n", "\n").strip()
    text = _strip_fence(text)
    preambles = _UNIVERSAL_PREAMBLES + list(pack.preamble_patterns)
    trailers = _UNIVERSAL_TRAILERS + list(pack.trailer_patterns)
    lines = text.split("\n")

    removed = 0  # at most three lines, so that no real text is ever lost in bulk
    while lines and removed < 3:
        head = lines[0].strip()
        if not head:
            lines.pop(0)
        elif _matches(head, preambles):
            lines.pop(0)
            removed += 1
        else:
            break
    removed = 0
    while lines and removed < 2:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
        elif _matches(tail, trailers):
            lines.pop()
            removed += 1
        else:
            break
    return _strip_enclosing_quotes("\n".join(lines).strip(), pack).strip()


def looks_like_meta(text: str, pack: LanguagePack) -> bool:
    """Does the answer talk about the task instead of being the text? Used for one retry."""
    if not text or not text.strip():
        return True
    first = text.strip().split("\n", 1)[0].strip()
    return _matches(first, _UNIVERSAL_PREAMBLES + list(pack.preamble_patterns))

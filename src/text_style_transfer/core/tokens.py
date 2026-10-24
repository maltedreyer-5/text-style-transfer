# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Offline token estimate.

No tokenizer is downloaded: the exact count depends on the model behind the
configured endpoint anyway. One token per three characters overestimates
for most European languages, which keeps limits on the safe side. After a
run, the UI shows the actual usage reported by the endpoint.
"""

from __future__ import annotations

import math

CHARS_PER_TOKEN = 3.0
TOKENS_PER_WORD = 1.6


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text or "") / CHARS_PER_TOKEN)


def output_budget(target_words: int, factor: float, minimum: int, maximum: int) -> int:
    """max_tokens for a step, derived from the target length."""
    return max(minimum, min(maximum, int(target_words * TOKENS_PER_WORD * factor)))

# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Client for an OpenAI-compatible chat-completions endpoint.

There is exactly one retry layer, this one. The SDK's own retries are
switched off (max_retries=0); stacked retry layers multiply the attempts
and put several times the load on a shared server during an outage.
Only transient failures are retried: connection errors, timeouts, 429 and
5xx. An overall deadline bounds the total waiting time per call.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import openai

from ..config import Config

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class Reply:
    text: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    attempts: int


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError)):
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


def _classify(exc: Exception, attempts: int) -> LLMError:
    if isinstance(exc, openai.APITimeoutError):
        return LLMError("llm_timeout", attempts=attempts)
    if isinstance(exc, openai.APIConnectionError):
        return LLMError("llm_unreachable", attempts=attempts)
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return LLMError("llm_auth")
    if isinstance(exc, openai.NotFoundError):
        return LLMError("llm_not_found")
    if isinstance(exc, openai.BadRequestError):
        return LLMError("llm_bad_request")
    if isinstance(exc, openai.APIStatusError):
        return LLMError("llm_status", status=exc.status_code, attempts=attempts)
    return LLMError("llm_failed", attempts=attempts)


class LLMClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = openai.OpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            timeout=config.llm_timeout,
            max_retries=0,
        )

    def chat(self, system: str, user: str, max_tokens: int) -> Reply:
        cfg = self.config
        params: dict = {
            "model": cfg.llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
        }
        if cfg.llm_extra_body:
            params["extra_body"] = cfg.llm_extra_body

        deadline = time.monotonic() + cfg.llm_deadline
        empty_retry_used = False
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                response = self.client.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001 - classified below, never shown raw
                log.warning("llm call failed: %s (attempt %d)", type(exc).__name__, attempt)
                if not _retryable(exc) or attempt >= cfg.llm_max_attempts:
                    raise _classify(exc, attempt) from None
                delay = cfg.llm_retry_delay * (2 ** (attempt - 1))
                if time.monotonic() + delay >= deadline:
                    raise LLMError("llm_deadline", attempts=attempt) from None
                time.sleep(delay)
                continue

            log.info("llm call ok in %.1fs (attempt %d)", time.monotonic() - started, attempt)
            choice = response.choices[0] if response.choices else None
            # Only the content is read. Reasoning fields that some servers add
            # next to it are ignored on purpose; reasoning tags inside the
            # content are removed by the cleanup step.
            text = (choice.message.content or "") if choice and choice.message else ""
            finish = choice.finish_reason if choice else None
            usage = response.usage
            if not text.strip():
                if finish == "length":
                    raise LLMError("llm_budget_exhausted")
                # An empty answer without a reason is usually a transient
                # server hiccup: one more attempt, then give up.
                if not empty_retry_used and time.monotonic() < deadline:
                    empty_retry_used = True
                    continue
                raise LLMError("llm_empty")
            return Reply(
                text=text,
                finish_reason=finish,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                attempts=attempt,
            )

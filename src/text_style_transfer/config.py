# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Runtime configuration from environment variables (prefix TST_).

Invalid values stop the start with a clear message instead of falling back
to a default: a silently ignored setting is harder to diagnose than a
refusal to start.

No sampling parameters (temperature, top_p, seed) are sent by default, so
the defaults of the server and model apply. Any such parameter can be set
through TST_LLM_EXTRA_BODY, which is merged into every request.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

PREFIX = "TST_"


class ConfigError(ValueError):
    pass


def _size(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+)\s*(kb|mb|b)?\s*", value.lower())
    if not match:
        raise ConfigError(f"invalid size {value!r} (examples: 500kb, 5mb)")
    number, unit = int(match.group(1)), match.group(2) or "b"
    return number * {"b": 1, "kb": 1024, "mb": 1024 * 1024}[unit]


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 7860
    root_path: str = ""
    llm_base_url: str = "http://localhost:8000/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "local-model"
    llm_timeout: float = 120.0
    llm_max_attempts: int = 3
    llm_retry_delay: float = 2.0
    llm_deadline: float = 300.0
    llm_extra_body: dict = field(default_factory=dict)
    llm_concurrency: int = 2
    max_input_tokens: int = 10000
    min_input_tokens: int = 20
    output_token_factor: float = 2.5
    output_token_min: int = 512
    output_token_max: int = 8000
    max_upload_bytes: int = 5 * 1024 * 1024
    session_ttl: int = 3600
    temp_ttl: int = 1800
    history_size: int = 20
    auth_header: str = ""
    profile_dir: Path | None = None
    privacy_notice_file: Path | None = None
    security_headers: bool = True

    @property
    def llm_host(self) -> str:
        return urlparse(self.llm_base_url).hostname or self.llm_base_url

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        defaults = cls()

        def get(name: str) -> str | None:
            value = env.get(PREFIX + name)
            return value.strip() if value is not None and value.strip() != "" else None

        def integer(name: str, default: int, low: int, high: int) -> int:
            raw = get(name)
            if raw is None:
                return default
            try:
                value = int(raw)
            except ValueError:
                raise ConfigError(f"{PREFIX}{name}: integer expected, got {raw!r}") from None
            if not low <= value <= high:
                raise ConfigError(f"{PREFIX}{name}: must be between {low} and {high}")
            return value

        def number(name: str, default: float | None, low: float, high: float) -> float | None:
            raw = get(name)
            if raw is None:
                return default
            try:
                value = float(raw)
            except ValueError:
                raise ConfigError(f"{PREFIX}{name}: number expected, got {raw!r}") from None
            if not low <= value <= high:
                raise ConfigError(f"{PREFIX}{name}: must be between {low} and {high}")
            return value

        def boolean(name: str, default: bool) -> bool:
            raw = get(name)
            if raw is None:
                return default
            if raw.lower() in ("1", "true", "yes", "on"):
                return True
            if raw.lower() in ("0", "false", "no", "off"):
                return False
            raise ConfigError(f"{PREFIX}{name}: true or false expected, got {raw!r}")

        def path(name: str) -> Path | None:
            raw = get(name)
            return Path(raw).expanduser() if raw else None

        extra_raw = get("LLM_EXTRA_BODY")
        extra: dict = {}
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"{PREFIX}LLM_EXTRA_BODY: invalid JSON ({exc.msg})") from None
            if not isinstance(extra, dict):
                raise ConfigError(f"{PREFIX}LLM_EXTRA_BODY: a JSON object is required")

        base_url = get("LLM_BASE_URL") or defaults.llm_base_url
        if urlparse(base_url).scheme not in ("http", "https"):
            raise ConfigError(f"{PREFIX}LLM_BASE_URL: http or https URL required")

        root = get("ROOT_PATH") or ""
        if root and not root.startswith("/"):
            raise ConfigError(f"{PREFIX}ROOT_PATH: must start with '/'")

        auth_header = (get("AUTH_HEADER") or "").lower()
        profile_dir = path("PROFILE_DIR")
        if profile_dir is not None and not profile_dir.is_dir():
            raise ConfigError(f"{PREFIX}PROFILE_DIR: directory not found")

        notice = path("PRIVACY_NOTICE_FILE")
        if notice is not None and not notice.is_file():
            raise ConfigError(f"{PREFIX}PRIVACY_NOTICE_FILE: file not found")

        cfg = cls(
            host=get("HOST") or defaults.host,
            port=integer("PORT", defaults.port, 1, 65535),
            root_path=root.rstrip("/"),
            llm_base_url=base_url,
            llm_api_key=get("LLM_API_KEY") or defaults.llm_api_key,
            llm_model=get("LLM_MODEL") or defaults.llm_model,
            llm_timeout=number("LLM_TIMEOUT", defaults.llm_timeout, 1, 3600),  # type: ignore[arg-type]
            llm_max_attempts=integer("LLM_MAX_ATTEMPTS", defaults.llm_max_attempts, 1, 10),
            llm_retry_delay=number("LLM_RETRY_DELAY", defaults.llm_retry_delay, 0, 60),  # type: ignore[arg-type]
            llm_deadline=number("LLM_DEADLINE", defaults.llm_deadline, 1, 7200),  # type: ignore[arg-type]
            llm_extra_body=extra,
            llm_concurrency=integer("LLM_CONCURRENCY", defaults.llm_concurrency, 1, 64),
            max_input_tokens=integer("MAX_INPUT_TOKENS", defaults.max_input_tokens, 100, 1_000_000),
            min_input_tokens=integer("MIN_INPUT_TOKENS", defaults.min_input_tokens, 1, 10_000),
            output_token_factor=number("OUTPUT_TOKEN_FACTOR", 2.5, 1, 20),  # type: ignore[arg-type]
            output_token_min=integer("OUTPUT_TOKEN_MIN", defaults.output_token_min, 16, 1_000_000),
            output_token_max=integer("OUTPUT_TOKEN_MAX", defaults.output_token_max, 16, 1_000_000),
            max_upload_bytes=_size(get("MAX_UPLOAD") or "5mb"),
            session_ttl=integer("SESSION_TTL", defaults.session_ttl, 60, 7 * 86400),
            temp_ttl=integer("TEMP_TTL", defaults.temp_ttl, 60, 7 * 86400),
            history_size=integer("HISTORY_SIZE", defaults.history_size, 1, 200),
            auth_header=auth_header,
            profile_dir=profile_dir,
            privacy_notice_file=notice,
            security_headers=boolean("SECURITY_HEADERS", True),
        )
        if cfg.output_token_min > cfg.output_token_max:
            raise ConfigError(f"{PREFIX}OUTPUT_TOKEN_MIN must not exceed {PREFIX}OUTPUT_TOKEN_MAX")
        return cfg

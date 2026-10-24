# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Profile code, version 1: a profile as one copy-and-paste line.

Layout:  tsp1.<base64url(zlib(canonical JSON))>.<crc32 as 8 hex digits>

The checksum detects truncated or mistyped codes. It is not a signature:
a code proves nothing about who made it, so free text from a code (style
description, rules, custom sliders) is shown to the user before it is used.
Both size limits are enforced before and during decompression so that a
crafted code cannot exhaust memory.
"""

from __future__ import annotations

import base64
import binascii
import json
import zlib

PREFIX = "tsp1"
MAX_CODE_CHARS = 24 * 1024
MAX_JSON_BYTES = 64 * 1024


class ProfileCodeError(ValueError):
    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def _canonical(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def encode(data: dict) -> str:
    raw = _canonical(data)
    if len(raw) > MAX_JSON_BYTES:
        raise ProfileCodeError("code_too_large")
    payload = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")
    return f"{PREFIX}.{payload}.{binascii.crc32(raw) & 0xFFFFFFFF:08x}"


def decode(code: str) -> dict:
    code = "".join((code or "").split())  # tolerate line breaks from copy and paste
    if not code:
        raise ProfileCodeError("code_empty")
    if len(code) > MAX_CODE_CHARS:
        raise ProfileCodeError("code_too_large")
    parts = code.split(".")
    if len(parts) != 3 or not parts[0].startswith("tsp"):
        raise ProfileCodeError("code_malformed")
    if parts[0] != PREFIX:
        raise ProfileCodeError("code_unsupported_version", version=parts[0][:8])
    payload, checksum = parts[1], parts[2]
    try:
        compressed = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, MAX_JSON_BYTES + 1)
    except (binascii.Error, ValueError, zlib.error):
        raise ProfileCodeError("code_malformed") from None
    if len(raw) > MAX_JSON_BYTES or inflater.unconsumed_tail:
        raise ProfileCodeError("code_too_large")
    if f"{binascii.crc32(raw) & 0xFFFFFFFF:08x}" != checksum.lower():
        raise ProfileCodeError("code_checksum")
    try:
        data = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProfileCodeError("code_malformed") from None
    if not isinstance(data, dict):
        raise ProfileCodeError("code_malformed")
    return data

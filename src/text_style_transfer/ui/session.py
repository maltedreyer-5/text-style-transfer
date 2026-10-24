# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Per-session state.

All data a user produces lives in one SessionData object held by gr.State,
which Gradio keeps per browser session and drops when the tab is closed or
the time-to-live expires. Nothing user-related is kept at module level, so
one session can never see another session's data.

Files offered for download are written to a directory of their own per
session and removed together with the session.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..core.models import Profile

log = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    time: str
    profile: str
    path: str
    language: str
    source: str
    neutral: str | None
    output: str


@dataclass
class SessionData:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    history: list[HistoryEntry] = field(default_factory=list)
    neutral_cache: dict[str, str] = field(default_factory=dict)
    last_neutral_key: str | None = None
    profile: Profile | None = None
    pairs: list[tuple[str, str]] = field(default_factory=list)
    wizard_previous: tuple[str, str] | None = None     # last result and table of the guided tab


class TempArea:
    """A private temporary directory with one sub-directory per session."""

    def __init__(self, root: Path, ttl: int) -> None:
        self.root = root
        self.ttl = ttl
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def folder(self, session: SessionData) -> Path:
        path = self.root / session.id
        path.mkdir(mode=0o700, exist_ok=True)
        return path

    def remove(self, session: SessionData | None) -> None:
        if session is not None:
            shutil.rmtree(self.root / session.id, ignore_errors=True)

    def sweep(self) -> None:
        """Remove session folders that have not been touched within the TTL."""
        limit = time.time() - self.ttl
        for child in self.root.iterdir():
            try:
                if child.is_dir() and child.stat().st_mtime < limit:
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                continue

    def destroy(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def ensure(session: SessionData | None) -> SessionData:
    return session if isinstance(session, SessionData) else SessionData()


def delete_upload(path: str | None) -> None:
    """Remove an uploaded file right after it was read (see core.documents)."""
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not delete upload: %s", type(exc).__name__)

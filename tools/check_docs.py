# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Check that every relative link and anchor in the Markdown files resolves."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
SKIP = {".git", "node_modules", ".venv", "venv", "build", "dist"}


def anchors(path: Path) -> set[str]:
    result = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip().lower()
            slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
            result.add(slug)
    return result


def main() -> int:
    errors = []
    files = [p for p in ROOT.rglob("*.md") if not SKIP & set(p.relative_to(ROOT).parts)
             and p.name != "RELEASE-CHECKLIST.md"]
    for md in files:
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target):
                continue  # external URL or mailto
            path_part, _, anchor = target.partition("#")
            dest = (md.parent / path_part).resolve() if path_part else md
            if not dest.exists():
                errors.append(f"{md.relative_to(ROOT)}: missing {target}")
            elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
                errors.append(f"{md.relative_to(ROOT)}: missing anchor {target}")
    for e in errors:
        print(e)
    print(f"checked {len(files)} Markdown files: {'OK' if not errors else f'{len(errors)} problem(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

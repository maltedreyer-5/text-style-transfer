# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Repository checks that tests cannot express:

1. no runtime state, build output or secrets in the tree
2. every Python file carries an SPDX header
3. the version is the same everywhere
4. the documentation does not refer to an unpublished history
5. every JSON, YAML and TOML file parses (an invalid issue template is
   silently not offered by GitHub)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [
    r"(^|/)\.env$", r"(^|/)\.env\.(?!example$)[^/]+$", r"__pycache__", r"\.py[cod]$", r"\.egg-info(/|$)",
    r"(^|/)(build|dist)/", r"(^|/)\.(pytest|ruff|mypy)_cache", r"\.log$", r"(^|/)text-style-result\.",
    r"(^|/)\.idea/", r"(^|/)\.vscode/", r"(^|/)RELEASE-CHECKLIST\.md$",
]
HISTORY = re.compile(
    r"\b(since version|since v\d|previously|formerly|used to be|no longer|fixed in|in earlier versions|"
    r"was changed|has been changed|früher|seit version|behoben in|nicht mehr)\b", re.IGNORECASE)
HISTORY_FILES = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "docs"]


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        # Not a git checkout (e.g. an unpacked archive): every file counts.
        return [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def main() -> int:
    problems: list[str] = []
    files = tracked_files()
    for name in files:
        if any(re.search(p, name) for p in FORBIDDEN):
            problems.append(f"runtime or private file in tree: {name}")
    for name in files:
        if name.endswith(".py"):
            head = (ROOT / name).read_text(encoding="utf-8").splitlines()[:3]
            if not any("SPDX-License-Identifier: MIT" in line for line in head):
                problems.append(f"missing SPDX header: {name}")

    init = (ROOT / "src/text_style_transfer/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__ = "([^"]+)"', init).group(1)
    changelog = re.search(r"^## \[?(\d+\.\d+\.\d+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    citation = re.search(r"^version: \"?([^\"\n]+)", (ROOT / "CITATION.cff").read_text(encoding="utf-8"), re.M)
    compose = re.search(r"image: text-style-transfer:([^\s]+)", (ROOT / "compose.yaml").read_text(encoding="utf-8"))
    for label, found in (("CHANGELOG.md", changelog), ("CITATION.cff", citation), ("compose.yaml", compose)):
        if not found or found.group(1).strip() != version:
            problems.append(f"version mismatch: {label} vs __version__ {version}")

    for entry in HISTORY_FILES:
        path = ROOT / entry
        for md in ([path] if path.is_file() else sorted(path.rglob("*.md"))):
            for no, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                if HISTORY.search(line):
                    problems.append(f"reference to history: {md.relative_to(ROOT)}:{no}: {line.strip()[:80]}")

    import json
    import tomllib

    import yaml  # installed with Gradio

    for name in files:
        path = ROOT / name
        try:
            if name.endswith(".json"):
                json.loads(path.read_text(encoding="utf-8"))
            elif name.endswith((".yml", ".yaml", ".cff")):
                yaml.safe_load(path.read_text(encoding="utf-8"))
            elif name.endswith(".toml"):
                tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report every parse error
            problems.append(f"does not parse: {name}: {type(exc).__name__}")

    for p in problems:
        print(p)
    print(f"checked {len(files)} files: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

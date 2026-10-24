# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Command-line starter: text-style-transfer [--host HOST] [--port PORT]."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="text-style-transfer", description="Start the web interface.")
    parser.add_argument("--host", help="address to bind to (overrides TST_HOST)")
    parser.add_argument("--port", type=int, help="port (overrides TST_PORT)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # Read .env from the current directory only. load_dotenv() without a path
    # searches upwards from this file, i.e. inside the installed package.
    from dotenv import load_dotenv

    load_dotenv(Path.cwd() / ".env", override=False)
    if args.host:
        os.environ["TST_HOST"] = args.host
    if args.port:
        os.environ["TST_PORT"] = str(args.port)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .config import Config, ConfigError

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    from .core.catalog import CatalogError
    from .ui.app import launch

    # docker stop and systemd send SIGTERM. Python's default handling ends the
    # process without running exit handlers, which would leave the temporary
    # directory behind; treating it like Ctrl+C runs the regular shutdown.
    def _terminate(_signum, _frame):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminate)

    try:
        launch(config)
    except CatalogError as exc:
        print(f"data error: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        # A stop signal during start-up, before the server runs: end without a
        # traceback; exit handlers still remove what was created.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

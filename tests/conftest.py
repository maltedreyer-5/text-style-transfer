# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from text_style_transfer.config import Config  # noqa: E402
from text_style_transfer.core.catalog import load_catalog  # noqa: E402


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


def make_config(url: str, **overrides) -> Config:
    env = {"TST_LLM_BASE_URL": url, "TST_LLM_RETRY_DELAY": "0", "TST_LLM_TIMEOUT": "5"}
    env.update({f"TST_{k.upper()}": str(v) for k, v in overrides.items()})
    return Config.from_env(env)

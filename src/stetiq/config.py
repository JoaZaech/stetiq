"""The repo config file (`stetiq.yaml`). Each feature parses only its own top-level
section (`entry_point`, `gates`, `drift`, ...); unknown keys are ignored here."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = "stetiq.yaml"


def load_config(path: str | os.PathLike[str] = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """The raw YAML mapping of the repo config file (empty file: `{}`)."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the repo config must be a YAML mapping")
    return data

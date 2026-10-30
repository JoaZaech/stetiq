"""The repo config file (`stetiq.yaml`): one raw YAML mapping shared by several features.

Each feature parses and validates only its own top-level section (`gates:`,
`entry_point:`, `drift:`, ...) in its own module; unknown top-level keys are ignored.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = "stetiq.yaml"


def load_config(path: str | os.PathLike[str] = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """The config file as a raw mapping (empty file -> {})."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the stetiq config file must be a YAML mapping")
    return data

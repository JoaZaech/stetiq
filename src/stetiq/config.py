"""The repo config file (`stetiq.yaml`): loading only.

Each feature parses and validates its own top-level section in its own module
(`drift:` in `stetiq.drift`, ...); unknown top-level keys are ignored here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """The raw YAML mapping in `path` ({} for an empty file)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the stetiq config must be a YAML mapping")
    return data

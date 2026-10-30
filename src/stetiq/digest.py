"""Canonical JSON and content hashes of plain data (Ontologies, Use Cases).

Versioned content is identified by the SHA-256 of its canonical JSON, so identical
content registers as the same version whatever its key order or formatting."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()

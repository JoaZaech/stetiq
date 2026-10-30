"""Shared by the tests that check the user guide (docs/guide/*.md) against the real code."""

import re
from pathlib import Path

GUIDE = Path(__file__).resolve().parent.parent / "docs" / "guide"
_FENCE = re.compile(r"^```(\S*)[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def read_page(name: str) -> str:
    return (GUIDE / name).read_text(encoding="utf-8")


def code_blocks(markdown: str) -> list[tuple[str, str]]:
    """`(language, body)` of every fenced code block, in order; the language is lower-cased
    and empty when the fence names none."""
    return [(language.lower(), body) for language, body in _FENCE.findall(markdown)]

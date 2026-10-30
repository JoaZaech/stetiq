"""Every example config on the stetiq.yaml guide page parses with the real loaders."""

import re
from pathlib import Path

import pytest

from stetiq.config import load_config
from stetiq.drift import thresholds_from_config
from stetiq.entry_point import EntryPoint
from stetiq.gates import parse_gates

PAGE = Path(__file__).parent.parent / "docs" / "guide" / "06-stetiq-yaml.md"
_YAML_BLOCK = re.compile(r"^```ya?ml\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _examples() -> list[str]:
    return _YAML_BLOCK.findall(PAGE.read_text())


def test_the_page_has_example_configs():
    assert len(_examples()) >= 3


@pytest.mark.parametrize("index", range(len(_examples()) if PAGE.exists() else 0))
def test_example_config_parses_with_the_real_loaders(index, tmp_path):
    path = tmp_path / "stetiq.yaml"
    path.write_text(_examples()[index])

    config = load_config(path)

    if "knowledge_graph" in config:
        assert isinstance(config["knowledge_graph"], str) and config["knowledge_graph"]
    if "entry_point" in config:
        EntryPoint.from_config(config)
    thresholds_from_config(config)
    parse_gates(config.get("gates"))

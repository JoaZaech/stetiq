"""Every example config on the stetiq.yaml guide page parses with the real loaders."""

import pytest
from guide_pages import code_blocks, read_page

from stetiq.config import load_config
from stetiq.drift import thresholds_from_config
from stetiq.entry_point import EntryPoint
from stetiq.gates import parse_gates

EXAMPLES = [
    body
    for language, body in code_blocks(read_page("06-stetiq-yaml.md"))
    if language in {"yaml", "yml"}
]


def test_the_page_has_example_configs():
    assert len(EXAMPLES) >= 3


@pytest.mark.parametrize("example", EXAMPLES)
def test_example_config_parses_with_the_real_loaders(example, tmp_path):
    path = tmp_path / "stetiq.yaml"
    path.write_text(example, encoding="utf-8")

    config = load_config(path)

    if "knowledge_graph" in config:
        assert isinstance(config["knowledge_graph"], str) and config["knowledge_graph"]
    if "entry_point" in config:
        EntryPoint.from_config(config)
    thresholds_from_config(config)
    parse_gates(config.get("gates"))

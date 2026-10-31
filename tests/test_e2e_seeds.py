"""The Playwright seed registry: every scenario a spec picks resolves, an unknown one fails."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

E2E = Path(__file__).parents[1] / "frontend" / "e2e"
sys.path.insert(0, str(E2E))

import seeds  # noqa: E402


def spec_scenarios() -> list[str]:
    """Every name a spec passes as `test.use({ seed: '…' })`."""
    names = {
        name
        for spec in E2E.glob("*.spec.ts")
        for name in re.findall(r"seed: '([^']+)'", spec.read_text())
    }
    return sorted(names)


def test_specs_pick_scenarios():
    assert "support_lineage" in spec_scenarios()


@pytest.mark.parametrize("name", spec_scenarios())
def test_every_spec_scenario_resolves(name):
    assert callable(seeds.scenario(name))


def test_an_unknown_scenario_lists_the_known_ones():
    with pytest.raises(seeds.UnknownScenario, match=r"'nope'.*known: .*support_lineage"):
        seeds.scenario("nope")


def test_the_seed_script_rejects_an_unknown_scenario(tmp_path):
    result = subprocess.run(
        [sys.executable, str(E2E / "seed.py"), "nope", f"sqlite:///{tmp_path / 'stetiq.db'}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unknown seed scenario 'nope'" in result.stderr
    assert "ontology_map_search" in result.stderr

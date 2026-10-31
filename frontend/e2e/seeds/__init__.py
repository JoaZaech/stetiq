"""The Playwright seed scenarios, one module per feature area, behind a registry.

A scenario is a function that takes a local-mode `stetiq.Client` and returns a
JSON-serialisable dict (ids, version numbers, tokens...); `seed.py` prints it and the
test gets it as `stetiq.seeded`. A spec picks one by its function name with
`test.use({ seed: 'name' })`.

To add a scenario, write the function in the module of the feature it seeds and add it
to that module's `SCENARIOS` tuple. A new feature area gets its own module, named in
`MODULES` below. Helpers and Ontologies that several modules use go in `_shared.py`
(`issue_token` issues an API Token for a `mode: 'server'` test). A scenario that builds
on another one imports it from that module.
"""

from __future__ import annotations

from importlib import import_module

from ._shared import Scenario

MODULES = tuple(
    import_module(f".{name}", __name__)
    for name in (
        "auth",
        "construction_runs",
        "gates",
        "knowledge_graphs",
        "observations",
        "ontology_map",
        "ontology_versions",
        "use_case",
    )
)

SCENARIOS: dict[str, Scenario] = {
    scenario.__name__: scenario for module in MODULES for scenario in module.SCENARIOS
}


class UnknownScenario(LookupError):
    """No seed scenario has that name."""


def scenario(name: str) -> Scenario:
    """The scenario called `name`."""
    try:
        return SCENARIOS[name]
    except KeyError:
        known = ", ".join(sorted(SCENARIOS))
        raise UnknownScenario(f"unknown seed scenario {name!r}; known: {known}") from None

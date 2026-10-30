"""Construction Entry Point: the user's command stetiq invokes as a Construction Run.

stetiq starts the command and observes the Graph Source after it exits; it never
knows what the command does inside. Declared in the repo config file (`stetiq.yaml`):

    entry_point:
      command: python build_graph.py --ontology {ontology} --scope {graph_source}

`command` is a string (split like a shell would, without running a shell) or a list
of arguments. Placeholders, substituted inside each argument:

- `{ontology}`: path to a temporary stetiq YAML file holding the Declared Ontology
- `{graph_source}`: the bound Graph Source scope as JSON (`{"database": ..., "label": ..., "namespace": ...}`)
- `{database}`, `{label}`, `{namespace}`: the scope's parts (empty when unset)
- `{knowledge_graph}`, `{ontology_version}`, `{run_id}`

Connection details (`STETIQ_GRAPH_SOURCE_URI` etc.) are never substituted; the command
inherits the environment, so it can read them there itself.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any

from stetiq.errors import StetiqError

CONFIG_SECTION = "entry_point"
PLACEHOLDERS = (
    "ontology",
    "graph_source",
    "database",
    "label",
    "namespace",
    "knowledge_graph",
    "ontology_version",
    "run_id",
)
_PLACEHOLDER = re.compile(r"\{(" + "|".join(PLACEHOLDERS) + r")\}")


class InvalidEntryPointError(StetiqError, ValueError):
    """The repo config has no usable `entry_point` section."""


class EntryPointError(StetiqError):
    """The Construction Entry Point could not be started (e.g. command not found)."""


@dataclass(frozen=True)
class EntryPoint:
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.command or not all(isinstance(a, str) for a in self.command):
            raise InvalidEntryPointError(
                "entry_point.command must be a non-empty string or list of strings"
            )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> EntryPoint:
        """Parse the `entry_point` section of a loaded repo config mapping."""
        section = config.get(CONFIG_SECTION)
        if not isinstance(section, dict) or "command" not in section:
            raise InvalidEntryPointError(f"the repo config declares no {CONFIG_SECTION}.command")
        command = section["command"]
        if isinstance(command, str):
            return cls(tuple(shlex.split(command)))
        if isinstance(command, list):
            return cls(tuple(command))
        raise InvalidEntryPointError(
            "entry_point.command must be a non-empty string or list of strings"
        )

    def argv(self, values: dict[str, str]) -> list[str]:
        """The command with every placeholder replaced by `values[name]`."""
        return [_PLACEHOLDER.sub(lambda m: values[m.group(1)], arg) for arg in self.command]


def placeholder_values(
    *, ontology_path: str, scope, knowledge_graph: str, ontology_version: int, run_id: str
) -> dict[str, str]:
    return {
        "ontology": ontology_path,
        "graph_source": json.dumps(scope.to_dict()),
        "database": scope.database,
        "label": scope.label or "",
        "namespace": scope.namespace or "",
        "knowledge_graph": knowledge_graph,
        "ontology_version": str(ontology_version),
        "run_id": run_id,
    }

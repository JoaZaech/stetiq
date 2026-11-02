"""On stage: what `show.py` needs to run against the compose stack (docker-compose.yml).

Where the stack is (`stage_settings`, from the environment and compose's `.env`), the
check before each act that names a container that is down (`stack_check`, `StackDown`,
`naming_down`), the presenter's pause at each beat (`presenter_pause`), and the rewind
(`compose_rewind`), which goes through docker compose and stetiq's public CLI only.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import neo4j
import neo4j.exceptions

import stetiq
from plant_assistant.deploy import Graphs
from stetiq.graph_source import Neo4jGraphSource

SHOWCASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SHOWCASE_DIR / ".env"
# The edit token compose's `tokens` service issues for the show (with the public
# `stetiq token create` CLI) each time the stetiq server starts on a new volume.
TOKEN_FILE = SHOWCASE_DIR / ".show" / "tokens" / "show"
TRACKING_SERVICE = "stetiq"
TRACKING_VOLUME = "stetiq-data"  # the compose volume that holds stetiq's tracking database


class StackDown(Exception):
    """A container the show needs is down; `down` names each, as compose does."""

    def __init__(self, down: list[str], act: int) -> None:
        self.down = down
        self.act = act
        names = ", ".join(down)
        super().__init__(
            f"{names} {'is' if len(down) == 1 else 'are'} down: start "
            f"{'it' if len(down) == 1 else 'them'} with `docker compose up -d "
            f"{' '.join(down)}`, then `uv run python show.py --act {act}`"
        )


class RewindError(Exception):
    """A docker compose step of the rewind failed."""


# What a probe raises when its container does not answer.
_UNREACHABLE: tuple[type[Exception], ...] = (
    OSError,
    httpx.HTTPError,
    neo4j.exceptions.DriverError,
    neo4j.exceptions.Neo4jError,
)


@contextlib.contextmanager
def naming_down(check: Callable[[], list[str]] | None, act: int) -> Iterator[None]:
    """Within it, an error that a container going down caused is raised as `StackDown`,
    naming the container rather than the error; any other error is raised as it is."""
    try:
        yield
    except StackDown:
        raise
    except Exception as e:
        down = check() if check is not None else []
        if down:
            raise StackDown(down, act) from e
        raise


def stack_check(
    *, stetiq: httpx.Client, graphs: Graphs, assistant: httpx.Client
) -> Callable[[], list[str]]:
    """The check the show runs before each act: it returns the compose services that do
    not answer (none when the stack is up). `stetiq` and `assistant` are HTTP clients on
    the stetiq server's and the assistant's base URLs."""

    def http(client: httpx.Client, path: str) -> Callable[[], object]:
        return lambda: client.get(path).raise_for_status()

    probes: dict[str, Callable[[], object]] = {
        "stetiq": http(stetiq, "/health"),
        "graph-candidate": graphs.candidate.verify_connectivity,
        "graph-production": graphs.production.verify_connectivity,
        "assistant": http(assistant, "/api/status"),
    }

    def check() -> list[str]:
        down = []
        for service, probe in probes.items():
            try:
                probe()
            except _UNREACHABLE:
                down.append(service)
        return down

    return check


def presenter_pause(
    *, interactive: bool, read: Callable[[str], object] = input
) -> Callable[[str], None]:
    """The presenter's pause at a beat: wait for Enter (`read`) when `interactive`, never
    otherwise. When the input ends (Enter piped in, then EOF), the show carries on."""

    def pause(label: str) -> None:
        if not interactive:
            return
        with contextlib.suppress(EOFError):
            read(f"\n  [Enter] {label} ")
        if read is input and not sys.stdin.isatty():
            print()  # piped Enter is not echoed: end the prompt's line

    return pause


def _dotenv(path: Path = ENV_FILE) -> dict[str, str]:
    """The `KEY=value` lines of compose's `.env` (no quoting, no interpolation)."""
    if not path.exists():
        return {}
    pairs = (
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    return {key.strip(): value.strip() for key, value in pairs}


def stage_settings(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Where show.py finds the stack: the environment, else what compose's `.env` sets up
    (its host ports and the Neo4j password)."""
    env = dict(os.environ if environ is None else environ)
    dotenv = _dotenv()

    def port(name: str, default: str) -> str:
        return env.get(name) or dotenv.get(name) or default

    return {
        "STETIQ_TRACKING_URI": env.get("STETIQ_TRACKING_URI")
        or f"http://localhost:{port('STETIQ_PORT', '5000')}",
        "PLANT_CANDIDATE_URI": env.get("PLANT_CANDIDATE_URI")
        or f"bolt://localhost:{port('CANDIDATE_PORT', '7687')}",
        "PLANT_PRODUCTION_URI": env.get("PLANT_PRODUCTION_URI")
        or f"bolt://localhost:{port('PRODUCTION_PORT', '7688')}",
        "PLANT_ASSISTANT_URL": env.get("PLANT_ASSISTANT_URL")
        or f"http://localhost:{port('ASSISTANT_PORT', '8000')}",
        "NEO4J_USER": env.get("NEO4J_USER") or "neo4j",
        "NEO4J_PASSWORD": env.get("NEO4J_PASSWORD") or dotenv.get("NEO4J_PASSWORD", ""),
    }


def show_client(tracking_uri: str, graph: neo4j.Driver) -> stetiq.Client:
    """A client of the stetiq server with the token compose issued for the show, whose
    Graph Source is `graph`."""
    if not TOKEN_FILE.exists():
        raise RewindError(
            f"no API token in {TOKEN_FILE.relative_to(SHOWCASE_DIR)}: run `docker compose up`"
        )
    return stetiq.Client(
        tracking_uri, token=TOKEN_FILE.read_text().strip(), graph_source=Neo4jGraphSource(graph)
    )


def _run(*command: str) -> str:
    try:
        done = subprocess.run(
            list(command), text=True, capture_output=True, cwd=SHOWCASE_DIR, check=False
        )
    except FileNotFoundError:
        raise RewindError("the rewind needs the docker CLI on the PATH") from None
    if done.returncode != 0:
        raise RewindError(f"`{' '.join(command)}` failed: {done.stderr.strip()}")
    return done.stdout


def _compose(*args: str) -> str:
    return _run("docker", "compose", *args)


def compose_rewind(tracking_uri: str, candidate: neo4j.Driver) -> Callable[[], stetiq.Client]:
    """The rewind of stetiq as compose runs it: the `stetiq` service starts over on a new,
    empty data volume, the `tokens` service issues new tokens with stetiq's public CLI
    (`stetiq token create`), and the assistant restarts to read its new one. The rewind
    returns the show's new client, whose Graph Source is `candidate`."""

    def rewind() -> stetiq.Client:
        volume = json.loads(_compose("config", "--format", "json"))["volumes"][TRACKING_VOLUME]
        # The one-shot `tokens` container mounts the volume too.
        _compose("rm", "--force", "--stop", TRACKING_SERVICE, "tokens")
        _run("docker", "volume", "rm", volume["name"])
        _compose("up", "--detach", "--wait", TRACKING_SERVICE, "tokens")
        _compose("up", "--detach", "--wait", "--force-recreate", "--no-deps", "assistant")
        return show_client(tracking_uri, candidate)

    return rewind

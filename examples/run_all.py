"""Run every example walkthrough into ONE tracking database, so the web UI shows them
all side by side, one Knowledge Graph per example (plus their gold references).

    uv run python examples/run_all.py            # from the repository root
    uv run stetiq ui --tracking-uri sqlite:///.stetiq/examples.db --port 5055

Each example's own `demo.py` still works on its own (`cd examples/<name> && uv run
python demo.py`), with its own database. This runner only changes where the
walkthroughs record: every `run_demo()` gets the shared tracking URI, and every
file-backed graph database lands under `.stetiq/examples/`. Nothing else differs.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import shutil
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES_DIR.parent
DEFAULT_STATE = REPO_ROOT / ".stetiq"
DEFAULT_DB = DEFAULT_STATE / "examples.db"


def discover() -> list[Path]:
    """Every examples/<name>/demo.py, the plant walkthrough first (it is the reference)."""
    demos = sorted(p for p in EXAMPLES_DIR.glob("*/demo.py"))
    return sorted(demos, key=lambda p: (p.parent.name != "plant-kg", p.parent.name))


def load(demo_path: Path):
    """Import a demo module under a unique name, with its folder importable for the
    duration (each demo imports its own sibling modules by bare name)."""
    folder = demo_path.parent
    name = f"example_{folder.name.replace('-', '_')}_demo"
    spec = importlib.util.spec_from_file_location(name, demo_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(folder))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(folder))
    return module


def run_one(demo_path: Path, *, tracking_uri: str, state_dir: Path, quiet: bool) -> None:
    module = load(demo_path)
    parameters = inspect.signature(module.run_demo).parameters
    kwargs: dict[str, object] = {"tracking_uri": tracking_uri, "quiet": quiet}
    if "graph_file" in parameters:
        kwargs["graph_file"] = state_dir / f"{demo_path.parent.name}.json"
    if "llm_cache" in parameters:
        kwargs["llm_cache"] = state_dir / f"{demo_path.parent.name}-llm-cache"
    if "extractor" in parameters:
        kwargs["extractor"] = "rules"  # offline and deterministic, like the tests
    module.run_demo(**kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tracking-uri", default=f"sqlite:///{DEFAULT_DB}")
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE / "examples"),
        help="where the examples' file-backed graph databases go",
    )
    parser.add_argument("--only", nargs="*", help="example folder names to run (default: all)")
    parser.add_argument("--quiet", action="store_true", help="no act-by-act narration")
    parser.add_argument("--reset", action="store_true", help="delete the shared database first")
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    db = (
        Path(args.tracking_uri.removeprefix("sqlite:///"))
        if args.tracking_uri.startswith("sqlite:///")
        else None
    )
    if args.reset:
        if db is not None and db.exists():
            db.unlink()
        shutil.rmtree(state_dir, ignore_errors=True)
    elif db is not None and db.exists():
        print(f"{db} already holds the examples; pass --reset to start over", file=sys.stderr)
        return 1
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    demos = [d for d in discover() if not args.only or d.parent.name in args.only]
    for demo in demos:
        print(f"\n################ {demo.parent.name} ################", flush=True)
        run_one(demo, tracking_uri=args.tracking_uri, state_dir=state_dir, quiet=args.quiet)

    print(
        "\nAll examples recorded in one tracking database. Browse them together:",
        f"  uv run stetiq ui --tracking-uri {args.tracking_uri} --port 5055",
        sep="\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

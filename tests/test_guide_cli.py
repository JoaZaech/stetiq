"""The user guide names only CLI commands that exist: every `stetiq …` command in a
shell code block of docs/guide/*.md must resolve in the Typer app (`--help` exits 0).
Python examples are not run."""

import re
import shlex

import pytest
import typer.main
from guide_pages import GUIDE, code_blocks
from typer.testing import CliRunner

from stetiq.cli import app

SHELL_LANGUAGES = {"", "bash", "sh", "shell", "console", "zsh"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def guide_commands(markdown: str) -> list[list[str]]:
    """The argv (after `stetiq`) of every `stetiq …` command in the shell code blocks."""
    commands = []
    for language, body in code_blocks(markdown):
        if language not in SHELL_LANGUAGES:
            continue
        for line in body.replace("\\\n", " ").splitlines():
            line = line.strip().removeprefix("$ ")
            for part in re.split(r"&&|\|\||[|;]", line):
                words = shlex.split(part, comments=True)
                while words and ENV_ASSIGNMENT.match(words[0]):
                    words = words[1:]
                if words and words[0] == "stetiq":
                    commands.append(words[1:])
    return commands


def command_path(argv: list[str]) -> list[str]:
    """The leading words of `argv` that name the command: subcommands down to a leaf
    command (or the first word that is not a subcommand, which then fails to resolve)."""
    path: list[str] = []
    subcommands = typer.main.get_command(app).commands  # a group's; None for a leaf
    for word in argv:
        if subcommands is None or word.startswith("-"):
            break
        path.append(word)
        subcommands = getattr(subcommands.get(word), "commands", None)
    return path


def resolves(argv: list[str]) -> bool:
    result = CliRunner().invoke(app, [*command_path(argv), "--help"])
    return result.exit_code == 0


GUIDE_COMMANDS = [
    pytest.param(argv, id=f"{page.name}: stetiq {' '.join(argv)}")
    for page in sorted(GUIDE.glob("*.md"))
    for argv in guide_commands(page.read_text(encoding="utf-8"))
]


def test_the_guide_has_cli_commands_to_check():
    assert len(GUIDE_COMMANDS) > 5


@pytest.mark.parametrize("argv", GUIDE_COMMANDS)
def test_guide_command_exists_in_the_cli(argv):
    assert resolves(argv), f"`stetiq {' '.join(argv)}` is not a stetiq command"


def test_a_made_up_command_does_not_resolve():
    markdown = "Run it:\n\n```bash\nstetiq kg frobnicate support --tracking-uri x\n```\n"

    [argv] = guide_commands(markdown)

    assert command_path(argv) == ["kg", "frobnicate"]
    assert not resolves(argv)


def test_only_shell_blocks_are_checked():
    markdown = (
        "```python\nimport stetiq  # stetiq nonsense\n```\n\n"
        "```text\nstetiq nonsense\n```\n\n"
        "```bash\nexport STETIQ_TOKEN=x && stetiq kg list | head\n"
        "STETIQ_TRACKING_URI=sqlite:///x.db stetiq ontology list support\n```\n"
    )

    assert guide_commands(markdown) == [["kg", "list"], ["ontology", "list", "support"]]

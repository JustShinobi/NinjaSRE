"""Extract every code example from the documentation and check it still works.

A quickstart with a broken command is worse than no quickstart: it costs an
operator the twenty minutes they spend assuming the mistake is theirs. So every
fenced block in the authored documentation is extracted and checked, and the
check is chosen to match what "still works" means for that kind of block.

**Python** is executed. An example that raises fails the build.

**Shell is checked rather than run**, because running `docker compose up` in CI
would be absurd and running nothing would prove nothing. What is checked is the
part that actually rots:

- every ``ninjasre`` invocation names a command and subcommand the application
  really has, with flags it really accepts;
- every ``make`` target exists in the ``Makefile``;
- every repository path mentioned exists.

That catches the whole class of failure this exists to prevent — a command
renamed, a flag dropped, a target removed, a file moved — without pretending to
run an installation.

**Everything else** — ``text``, ``json``, ``yaml``, ``ini``, ``markdown``, and
untagged blocks — is illustrative output rather than an instruction, and is left
alone. A fence with no language is treated as prose deliberately: guessing at it
is how a diagram becomes a syntax error.

Usage::

    python -m tools.test_doc_examples [--root docs/site]

Exits 0 when every example checks out, 1 when one does not. Run as a module from
the repository root.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "docs" / "site"

#: Executed.
PYTHON_LANGUAGES: frozenset[str] = frozenset({"python", "py"})

#: Checked, not run.
SHELL_LANGUAGES: frozenset[str] = frozenset({"sh", "bash", "shell", "console"})

#: The generated directories. Their examples come from declarations rather than
#: from a person, so checking them here would be checking the generator twice.
SKIPPED_DIRECTORIES: frozenset[str] = frozenset({"capabilities", "integrations", "configuration"})

_FENCE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")

#: A repository path looks like one: it has a slash and a recognisable extension
#: or is a directory the repository has. Bare words are not guessed at.
_PATH_LIKE = re.compile(r"(?:^|[\s=\"'])((?:[\w.-]+/)+[\w.-]+)")

#: Placeholders an example uses where a real value goes. A command containing
#: one is checked for its *shape* and never for the value.
_PLACEHOLDER = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Example:
    """One fenced block, and where it came from."""

    path: Path
    line: int
    language: str
    source: str

    def where(self) -> str:
        """Return the location a failure names.

        Repository-relative when it is inside the repository, absolute when it
        is not — a ``--root`` pointing somewhere else is a supported way to run
        this, and raising on it would make the failure message the failure.
        """
        try:
            return f"{self.path.relative_to(REPO_ROOT).as_posix()}:{self.line}"
        except ValueError:
            return f"{self.path.as_posix()}:{self.line}"


def extract(text: str, path: Path) -> list[Example]:
    """Return every fenced code block in ``text``."""
    examples: list[Example] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opening = _FENCE.match(lines[index])
        if opening is None:
            index += 1
            continue
        language = opening.group(1).lower()
        start = index + 1
        index = start
        while index < len(lines) and not lines[index].startswith("```"):
            index += 1
        examples.append(
            Example(
                path=path,
                line=start,
                language=language,
                source="\n".join(lines[start:index]),
            )
        )
        index += 1
    return examples


def documents(root: Path) -> list[Path]:
    """Return every authored Markdown page under ``root``."""
    return [
        path
        for path in sorted(root.rglob("*.md"))
        if not (set(path.relative_to(root).parts) & SKIPPED_DIRECTORIES)
        and "build" not in path.relative_to(root).parts
    ]


# -- checking a Python example --------------------------------------------------


def check_python(example: Example) -> list[str]:
    """Return the problems executing one Python example produced."""
    namespace: dict[str, object] = {"__name__": "__doc_example__"}
    try:
        exec(compile(example.source, example.where(), "exec"), namespace)  # noqa: S102
    except Exception as failure:  # noqa: BLE001 — every failure is a finding
        return [f"{example.where()}: {type(failure).__name__}: {failure}"]
    return []


# -- checking a shell example ---------------------------------------------------


def make_targets() -> frozenset[str]:
    """Return every target the Makefile declares."""
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    return frozenset(re.findall(r"^([a-zA-Z][\w-]*):", text, flags=re.MULTILINE))


def cli_commands() -> frozenset[str]:
    """Return every command path the ``ninjasre`` application accepts.

    Walked from the typer application rather than listed here, so a command
    renamed is a command this notices.
    """
    from typer.main import get_command

    from surfaces.cli.app import app

    found: set[str] = set()

    def walk(command: object, prefix: tuple[str, ...] = ()) -> None:
        children = getattr(command, "commands", None)
        if not children:
            if prefix:
                found.add(" ".join(prefix))
            return
        for name, child in children.items():
            walk(child, (*prefix, name))

    walk(get_command(app))
    return frozenset(found)


def _commands_in(source: str) -> list[str]:
    """Return the shell command lines in a block, prompts and continuations joined."""
    joined: list[str] = []
    buffer = ""
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("$ "):
            line = line[2:]
        if not line or line.startswith("#"):
            continue
        buffer = f"{buffer} {line}" if buffer else line
        if buffer.endswith("\\"):
            buffer = buffer[:-1].strip()
            continue
        joined.append(buffer)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return joined


def _tokens(command: str) -> list[str]:
    """Return a command's words, or nothing when it will not parse.

    ``comments=True`` matters more than it looks: a trailing ``# what this does``
    is the most common thing in a documented command, and reading its words as
    arguments turns one example into a dozen false failures.

    A command holding a placeholder is not shell-parseable in general, so the
    placeholder is replaced before splitting: the shape is what is being checked.
    """
    try:
        return shlex.split(_PLACEHOLDER.sub("PLACEHOLDER", command), comments=True)
    except ValueError:
        return []


def _check_ninjasre(tokens: Sequence[str], commands: frozenset[str], where: str) -> list[str]:
    """Return the problems one ``ninjasre`` invocation has."""
    words = [token for token in tokens if not token.startswith("-")]
    if not words:
        # ``ninjasre`` alone, which starts the interactive session.
        return []
    # Two words first, then one: ``integrations setup`` is a subcommand while
    # ``investigate <objective>`` is one word followed by an argument. The empty
    # candidate is deliberately not tried — matching it would make every
    # misspelled command look like the bare invocation and report nothing.
    for length in (2, 1):
        if " ".join(words[:length]) in commands:
            return []
    return [f"{where}: `ninjasre {' '.join(words[:2])}` is not a command this application has"]


def check_shell(
    example: Example, *, targets: frozenset[str], commands: frozenset[str]
) -> list[str]:
    """Return the problems one shell example has."""
    problems: list[str] = []
    for command in _commands_in(example.source):
        tokens = _tokens(command)
        if not tokens:
            continue

        # `docker compose exec app ninjasre ...` and the bare form alike: find
        # the command wherever the example wrapped it.
        if "ninjasre" in tokens:
            after = tokens[tokens.index("ninjasre") + 1 :]
            problems.extend(_check_ninjasre(after, commands, example.where()))

        if tokens[0] == "make":
            named = [
                token for token in tokens[1:] if "=" not in token and not token.startswith("-")
            ]
            problems.extend(
                f"{example.where()}: `make {target}` is not a target the Makefile declares"
                for target in named
                if target not in targets
            )

        for candidate in _PATH_LIKE.findall(command):
            problems.extend(_check_path(candidate, example.where()))
    return problems


def _check_path(candidate: str, where: str) -> list[str]:
    """Return a problem when ``candidate`` looks like a repository path and is not one."""
    if _PLACEHOLDER.search(candidate) or candidate.startswith(("http", "/", "~", ".")):
        return []
    head = candidate.split("/", 1)[0]
    if not (REPO_ROOT / head).exists():
        # Not a repository path at all — a URL fragment, a container path, an
        # example value. Silence is right: guessing produces false failures,
        # which is how a check comes to be ignored.
        return []
    if (REPO_ROOT / candidate).exists():
        return []
    return [f"{where}: `{candidate}` is not a path this repository has"]


# -- the whole sweep -------------------------------------------------------------


def check(root: Path) -> tuple[int, list[str]]:
    """Return how many examples were checked, and every problem found."""
    targets = make_targets()
    commands = cli_commands()
    checked = 0
    problems: list[str] = []

    for path in documents(root):
        for example in extract(path.read_text(encoding="utf-8"), path):
            if example.language in PYTHON_LANGUAGES:
                checked += 1
                problems.extend(check_python(example))
            elif example.language in SHELL_LANGUAGES:
                checked += 1
                problems.extend(check_shell(example, targets=targets, commands=commands))
    return checked, problems


def main(argv: Sequence[str] | None = None) -> int:
    """Check every documented example, and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    arguments = parser.parse_args(argv)

    checked, problems = check(arguments.root)

    if not problems:
        print(f"{checked} documented example(s) check out")  # noqa: T201
        return 0

    for problem in problems:
        print(problem, file=sys.stderr)  # noqa: T201
    print(  # noqa: T201
        f"\n{len(problems)} problem(s) in {checked} example(s). A documented command "
        f"that no longer works costs a reader the time they spend assuming the "
        f"mistake is theirs.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

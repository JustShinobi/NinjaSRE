"""A Protocol method body is a docstring and nothing else.

FR-018. The failure this prevents is subtle and expensive: a `Protocol` method
whose body is `...` or `pass` type-checks fine, but if the class is ever
instantiated or subclassed concretely, the stub silently *becomes* the
implementation and returns `None`. A `raise NotImplementedError` is the same
mistake wearing a warning label — it turns a contract into a runtime landmine.

The contract is the signature and the docstring. Everything below it is filler
that can only do harm.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_protocol_bodies import (
    ELLIPSIS_BODY,
    NOT_IMPLEMENTED_BODY,
    PASS_BODY,
    find_violations,
)

pytestmark = pytest.mark.unit


def write(root: Path, source: str, name: str = "ports.py") -> Path:
    target = root / name
    target.write_text(source, encoding="utf-8")
    return target


PROTOCOL_PREAMBLE = "from typing import Protocol\n\n\n"


def protocol(body: str, bases: str = "Protocol") -> str:
    return f"{PROTOCOL_PREAMBLE}class EpisodeStore({bases}):\n{body}"


# --- The compliant form ------------------------------------------------------


def test_a_docstring_only_body_is_clean(tmp_path: Path) -> None:
    write(tmp_path, protocol('    def get(self, key: str) -> str:\n        """Return it."""\n'))

    assert find_violations([tmp_path]) == []


def test_a_multi_line_docstring_is_clean(tmp_path: Path) -> None:
    source = protocol(
        "    def get(self, key: str) -> str:\n"
        '        """Return the episode.\n\n'
        "        Raises:\n"
        "            KeyError: no such episode.\n"
        '        """\n'
    )
    write(tmp_path, source)

    assert find_violations([tmp_path]) == []


# --- The three fillers -------------------------------------------------------


def test_flags_an_ellipsis_body(tmp_path: Path) -> None:
    write(tmp_path, protocol("    def get(self, key: str) -> str:\n        ...\n"))

    violations = find_violations([tmp_path])

    assert [violation.rule for violation in violations] == [ELLIPSIS_BODY]
    assert violations[0].qualified_name == "EpisodeStore.get"


def test_flags_a_pass_body(tmp_path: Path) -> None:
    write(tmp_path, protocol("    def get(self, key: str) -> str:\n        pass\n"))

    assert [violation.rule for violation in find_violations([tmp_path])] == [PASS_BODY]


def test_flags_a_raise_not_implemented_body(tmp_path: Path) -> None:
    source = protocol("    def get(self, key: str) -> str:\n        raise NotImplementedError\n")
    write(tmp_path, source)

    assert [violation.rule for violation in find_violations([tmp_path])] == [NOT_IMPLEMENTED_BODY]


def test_flags_a_called_not_implemented_error(tmp_path: Path) -> None:
    source = protocol(
        '    def get(self, key: str) -> str:\n        raise NotImplementedError("subclass me")\n'
    )
    write(tmp_path, source)

    assert [violation.rule for violation in find_violations([tmp_path])] == [NOT_IMPLEMENTED_BODY]


# --- The docstring-then-filler case ------------------------------------------


def test_flags_a_docstring_followed_by_an_ellipsis(tmp_path: Path) -> None:
    """The form that reads as complete and is not."""
    source = protocol(
        '    def get(self, key: str) -> str:\n        """Return it."""\n        ...\n'
    )
    module = write(tmp_path, source)

    violations = find_violations([tmp_path])

    assert [violation.rule for violation in violations] == [ELLIPSIS_BODY]
    # The report points at the filler, not at the docstring above it.
    reported = module.read_text(encoding="utf-8").splitlines()[violations[0].line - 1]
    assert reported.strip() == "..."


def test_flags_a_docstring_followed_by_pass(tmp_path: Path) -> None:
    source = protocol(
        '    def get(self, key: str) -> str:\n        """Return it."""\n        pass\n'
    )
    write(tmp_path, source)

    assert [violation.rule for violation in find_violations([tmp_path])] == [PASS_BODY]


# --- Scope -------------------------------------------------------------------


def test_ignores_classes_that_are_not_protocols(tmp_path: Path) -> None:
    """An abstract base class is somebody else's argument."""
    write(tmp_path, "class Thing:\n    def get(self) -> None:\n        ...\n")

    assert find_violations([tmp_path]) == []


@pytest.mark.parametrize(
    "bases",
    ["Protocol", "typing.Protocol", "Protocol[T]", "Hashable, Protocol"],
    ids=["bare", "qualified", "generic", "mixed-in"],
)
def test_recognises_every_way_a_protocol_is_declared(tmp_path: Path, bases: str) -> None:
    write(tmp_path, protocol("    def get(self) -> None:\n        ...\n", bases=bases))

    assert [violation.rule for violation in find_violations([tmp_path])] == [ELLIPSIS_BODY]


def test_covers_async_methods(tmp_path: Path) -> None:
    write(tmp_path, protocol("    async def get(self) -> None:\n        ...\n"))

    assert [violation.rule for violation in find_violations([tmp_path])] == [ELLIPSIS_BODY]


def test_reports_each_offending_method_once(tmp_path: Path) -> None:
    source = protocol(
        "    def get(self) -> None:\n        ...\n\n"
        "    def put(self) -> None:\n        pass\n\n"
        '    def drop(self) -> None:\n        """Clean."""\n'
    )
    write(tmp_path, source)

    violations = find_violations([tmp_path])

    assert [violation.qualified_name for violation in violations] == [
        "EpisodeStore.get",
        "EpisodeStore.put",
    ]


def test_a_protocol_nested_in_a_class_is_still_a_protocol(tmp_path: Path) -> None:
    source = (
        f"{PROTOCOL_PREAMBLE}class Outer:\n"
        "    class Inner(Protocol):\n"
        "        def get(self) -> None:\n"
        "            ...\n"
    )
    write(tmp_path, source)

    assert [violation.rule for violation in find_violations([tmp_path])] == [ELLIPSIS_BODY]


# --- The repository itself ---------------------------------------------------


def test_the_repository_has_no_filled_protocol_bodies() -> None:
    from tools.check_protocol_bodies import DEFAULT_SCAN_ROOTS

    violations = find_violations(DEFAULT_SCAN_ROOTS)

    assert violations == [], "\n".join(str(violation) for violation in violations)

"""A forgotten comma in a metadata list is a silent merge, not a syntax error.

Two adjacent string literals concatenate. In prose metadata that reads as one
long entry rather than an error, and the entry that vanished was one of the
signals selection scores on — so the capability quietly stops matching the
incident it was written for, and nothing anywhere says so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_metadata_literals import find_violations, module_violations

pytestmark = pytest.mark.unit


CLEAN = """
from core.capability import tool

FINDING = (
    "A long sentence that lives in a module constant, which is where a long "
    "sentence belongs, and which is deliberately concatenated."
)

@tool(
    name="ok",
    use_cases=["find the failing endpoint", "list recent deploys", FINDING],
    anti_examples=["a question about billing"],
)
def ok() -> None:
    pass
"""

MISSING_COMMA = """
from core.capability import tool

@tool(
    name="broken",
    use_cases=[
        "find the failing endpoint"
        "list recent deploys",
    ],
)
def broken() -> None:
    pass
"""

MISSING_COMMA_IN_ASSIGNMENT = """
ANTI_EXAMPLES = (
    "a question about billing"
    "a request to change a password",
)
"""


def test_a_module_constant_may_still_be_concatenated() -> None:
    """The rule is about list entries, not about long strings.

    FR-020 asks for long prose to move into a module constant. A rule that also
    banned concatenation there would have made the remedy illegal.
    """
    assert module_violations(Path("clean.py"), CLEAN) == []


def test_a_forgotten_comma_in_a_use_case_list_is_reported() -> None:
    violations = module_violations(Path("broken.py"), MISSING_COMMA)

    assert len(violations) == 1
    assert violations[0].field == "use_cases"
    assert "broken.py" in str(violations[0])


def test_a_forgotten_comma_in_an_assigned_metadata_tuple_is_reported() -> None:
    violations = module_violations(Path("broken.py"), MISSING_COMMA_IN_ASSIGNMENT)

    assert len(violations) == 1
    assert violations[0].field == "ANTI_EXAMPLES"


def test_a_list_that_is_not_metadata_is_left_alone() -> None:
    """Implicit concatenation is idiomatic elsewhere; the rule is targeted."""
    source = 'MESSAGES = ["a long message that is deliberately " "split across lines"]\n'

    assert module_violations(Path("other.py"), source) == []


def test_the_report_names_the_line_and_the_field() -> None:
    violation = module_violations(Path("broken.py"), MISSING_COMMA)[0]

    rendered = str(violation)
    assert "use_cases" in rendered
    assert str(violation.line) in rendered


def test_the_repository_itself_is_clean() -> None:
    assert find_violations(None) == []

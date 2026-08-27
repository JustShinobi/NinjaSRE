"""Environment-variable names may only be written in the constants tier.

FR-009 puts every env-var name under ``config/constants/``; FR-010 makes that
checkable. The failure this prevents is small and constant: a module reaches for
``os.getenv("NINJASRE_...")`` inline, the name drifts from the one the operator
documentation promises, and nothing catches it until a deployment reads an
empty string.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_constants import ENV_LOOKUP_RULE, ENV_NAME_RULE, find_violations

pytestmark = pytest.mark.unit


def write_module(root: Path, relative: str, source: str) -> Path:
    """Write ``source`` to ``relative`` under ``root`` and return the path."""
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def test_flags_a_ninjasre_env_name_outside_the_constants_tier(tmp_path: Path) -> None:
    write_module(tmp_path, "core/agent/loop.py", 'HOME = "NINJASRE_HOME_DIR"\n')

    violations = find_violations([tmp_path])

    assert len(violations) == 1
    assert violations[0].name == "NINJASRE_HOME_DIR"
    assert violations[0].rule == ENV_NAME_RULE


def test_flags_a_vendor_env_name(tmp_path: Path) -> None:
    write_module(tmp_path, "core/llm/anthropic.py", 'KEY = "ANTHROPIC_API_KEY"\n')

    violations = find_violations([tmp_path])

    assert [violation.name for violation in violations] == ["ANTHROPIC_API_KEY"]


def test_flags_an_environment_lookup_whatever_the_name_looks_like(tmp_path: Path) -> None:
    """Rule two catches the lookup itself, so an unknown vendor cannot slip past."""
    write_module(
        tmp_path,
        "integrations/acme/client.py",
        "import os\n\nendpoint = os.getenv('acme_endpoint')\n",
    )

    violations = find_violations([tmp_path])

    assert len(violations) == 1
    assert violations[0].name == "acme_endpoint"
    assert violations[0].rule == ENV_LOOKUP_RULE


@pytest.mark.parametrize(
    "source",
    [
        "import os\n\nvalue = os.environ['SOME_KEY']\n",
        "import os\n\nvalue = os.environ.get('SOME_KEY')\n",
        "from os import environ\n\nvalue = environ['SOME_KEY']\n",
        "from os import getenv\n\nvalue = getenv('SOME_KEY')\n",
    ],
    ids=["subscript", "environ-get", "bare-environ", "bare-getenv"],
)
def test_flags_every_environment_lookup_form(tmp_path: Path, source: str) -> None:
    write_module(tmp_path, "platform/thing.py", source)

    violations = find_violations([tmp_path])

    assert [violation.name for violation in violations] == ["SOME_KEY"]


def test_allows_the_constants_tier_itself(tmp_path: Path) -> None:
    """The tier that owns the names is where the names are written."""
    write_module(
        tmp_path,
        "config/constants/paths.py",
        "import os\n\nNINJASRE_HOME_DIR_ENV = 'NINJASRE_HOME_DIR'\n"
        "value = os.environ.get(NINJASRE_HOME_DIR_ENV)\n",
    )

    assert find_violations([tmp_path]) == []


def test_allows_a_module_that_imports_the_constant(tmp_path: Path) -> None:
    """The compliant path: name the constant, never the string."""
    write_module(
        tmp_path,
        "platform/persistence/engine.py",
        "import os\n\n"
        "from config.constants.persistence import NINJASRE_DATABASE_URL_ENV\n\n"
        "url = os.environ.get(NINJASRE_DATABASE_URL_ENV)\n",
    )

    assert find_violations([tmp_path]) == []


@pytest.mark.parametrize(
    "literal",
    ["GET", "READ_ONLY", "root_cause_category", "X-NinjaSRE-Tenant", "SELECT_FOR_UPDATE"],
)
def test_allows_unrelated_upper_case_strings(tmp_path: Path, literal: str) -> None:
    """An env-var name is a specific thing, not every shouting string."""
    write_module(tmp_path, "core/domain/rules.py", f'VALUE = "{literal}"\n')

    assert find_violations([tmp_path]) == []


def test_reports_the_file_and_line(tmp_path: Path) -> None:
    """A violation has to be navigable, not merely true."""
    module = write_module(
        tmp_path,
        "surfaces/cli/app.py",
        "# a comment\n\nTOKEN = 'NINJASRE_API_TOKEN'\n",
    )

    (violation,) = find_violations([tmp_path])

    assert violation.path == module
    assert violation.line == 3


def test_scans_every_file_under_the_given_roots(tmp_path: Path) -> None:
    write_module(tmp_path, "core/one.py", 'A = "NINJASRE_ONE"\n')
    write_module(tmp_path, "gateway/nested/two.py", 'B = "NINJASRE_TWO"\n')

    violations = find_violations([tmp_path])

    assert sorted(violation.name for violation in violations) == [
        "NINJASRE_ONE",
        "NINJASRE_TWO",
    ]


def test_ignores_non_python_files(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("NINJASRE_HOME_DIR is the root.\n", encoding="utf-8")

    assert find_violations([tmp_path]) == []


@pytest.mark.sweep
def test_the_repository_itself_is_clean() -> None:
    """The rule holds for the code that ships, not only for fixtures."""
    from tools.check_constants import DEFAULT_SCAN_ROOTS

    violations = find_violations(DEFAULT_SCAN_ROOTS)

    assert violations == [], "\n".join(str(violation) for violation in violations)

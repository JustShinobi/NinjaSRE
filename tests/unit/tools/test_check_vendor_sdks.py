"""The vendor-SDK boundary check, including the ways round it.

The check earns its place only if it catches the *accidental* workaround. A
contributor who cannot `import openai` in a pipeline stage and reaches for
`importlib.import_module("openai")` is not evading a rule, they are solving a
problem — and the boundary is gone either way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_vendor_sdks import (
    VENDOR_DYNAMIC_IMPORT_RULE,
    VENDOR_IMPORT_RULE,
    VENDOR_MODULES,
    find_violations,
    is_allowed,
    is_vendor,
    module_violations,
    root_module,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path",
    [
        Path("core/llm/providers/anthropic.py"),
        Path("core/llm/transports/sdk.py"),
        Path("/srv/checkout/core/llm/client.py"),
    ],
)
def test_the_provider_layer_is_allowed_to_know_about_vendors(path: Path) -> None:
    assert is_allowed(path) is True


@pytest.mark.parametrize(
    "path",
    [
        Path("core/pipeline/diagnose.py"),
        Path("capabilities/tools/grafana.py"),
        Path("platform/memory/episodic.py"),
        Path("surfaces/cli/main.py"),
        # Nearly right, and therefore worth pinning: a package called `llm`
        # somewhere else is not the provider layer.
        Path("integrations/llm/client.py"),
    ],
)
def test_everywhere_else_is_not(path: Path) -> None:
    assert is_allowed(path) is False


@pytest.mark.parametrize("module", sorted(VENDOR_MODULES))
def test_every_listed_module_is_recognised(module: str) -> None:
    assert is_vendor(module) is True
    assert is_vendor(f"{module}.types.chat") is True


@pytest.mark.parametrize("module", ["structlog", "pytest", "core", "config", "collections.abc"])
def test_an_ordinary_dependency_is_not_a_vendor_sdk(module: str) -> None:
    assert is_vendor(module) is False


def test_a_submodule_resolves_to_its_distribution() -> None:
    assert root_module("google.genai.types") == "google"


def test_a_plain_import_is_caught() -> None:
    violations = module_violations(Path("core/pipeline/diagnose.py"), "import anthropic\n")

    assert [violation.rule for violation in violations] == [VENDOR_IMPORT_RULE]
    assert violations[0].module == "anthropic"


def test_a_from_import_is_caught() -> None:
    violations = module_violations(
        Path("core/pipeline/diagnose.py"), "from openai import AsyncOpenAI\n"
    )

    assert [violation.module for violation in violations] == ["openai"]


def test_a_submodule_import_is_caught() -> None:
    violations = module_violations(
        Path("core/pipeline/diagnose.py"), "from google.genai import Client\n"
    )

    assert [violation.module for violation in violations] == ["google.genai"]


@pytest.mark.parametrize(
    "source",
    [
        'import importlib\nmodule = importlib.import_module("anthropic")\n',
        'module = __import__("openai")\n',
        'from importlib import import_module\nmodule = import_module("boto3")\n',
    ],
)
def test_the_dynamic_workaround_is_caught(source: str) -> None:
    """The rule that actually holds the line."""
    violations = module_violations(Path("core/pipeline/diagnose.py"), source)

    assert [violation.rule for violation in violations] == [VENDOR_DYNAMIC_IMPORT_RULE]


def test_a_dynamic_import_of_something_ordinary_is_fine() -> None:
    source = 'import importlib\nmodule = importlib.import_module("json")\n'

    assert module_violations(Path("core/pipeline/diagnose.py"), source) == []


def test_a_relative_import_is_not_mistaken_for_a_vendor(tmp_path: Path) -> None:
    """``from .openai import x`` is a local module, whatever it is called."""
    source = "from .openai import Adapter\n"

    assert module_violations(Path("core/pipeline/diagnose.py"), source) == []


def test_the_repository_is_clean() -> None:
    """The rule holds right now, which is the only version of it that matters."""
    from tools.check_vendor_sdks import DEFAULT_SCAN_ROOTS

    violations = find_violations(DEFAULT_SCAN_ROOTS)

    assert not violations, "\n".join(str(violation) for violation in violations)


def test_a_violation_anywhere_under_a_scanned_root_is_found(tmp_path: Path) -> None:
    offender = tmp_path / "capabilities" / "tools" / "grafana.py"
    offender.parent.mkdir(parents=True)
    offender.write_text("import anthropic\n", encoding="utf-8")

    allowed = tmp_path / "core" / "llm" / "providers" / "anthropic.py"
    allowed.parent.mkdir(parents=True)
    allowed.write_text("import anthropic\n", encoding="utf-8")

    violations = find_violations([tmp_path])

    assert [violation.path for violation in violations] == [offender]


def test_the_report_names_the_file_the_line_and_the_module() -> None:
    violation = module_violations(Path("core/pipeline/diagnose.py"), "\n\nimport openai\n")[0]

    rendered = str(violation)
    assert "core" in rendered and "diagnose.py" in rendered
    assert ":3:" in rendered
    assert "'openai'" in rendered

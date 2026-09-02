"""Each thing the design system claims, and the test that proves it.

The design system's proofs live in the console's own suites — TypeScript unit
tests, a browser suite, and a pixel comparison — none of which pytest runs. That
is fine and deliberate: they run in the same ``make verify``, through the console
gate. What is not fine is a criterion whose proof gets renamed or deleted and
nobody notices, because the map from claim to proof would then live only in a
document nobody reads.

So this module is the map, and it fails when a proof stops existing. It reads
committed text and needs no toolchain, which means it holds on every machine and
in every job — including the ones where the console checks themselves skip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from config.constants.console import (
    CONSOLE_ICON_BUDGET_BYTES,
    CONSOLE_STYLESHEET_BUDGET_BYTES,
)
from tools.console_budget import icon_bytes, measure
from tools.console_gate import ORDER
from tools.console_toolchain import REPO_ROOT, console_root

pytestmark = pytest.mark.contract

CONSOLE = console_root()


@dataclass(frozen=True, slots=True)
class Claim:
    """One criterion, and the named test that holds it."""

    criterion: str
    claim: str
    module: str
    test: str


#: Every success criterion of the design system, against its proof.
CLAIMS = (
    Claim(
        "SC-001",
        "every pair in both themes passes its threshold, from the tokens rather than a screenshot",
        "console/tests/unit/design/contrast.test.ts",
        "reaches 4.5:1 on every pair a viewer reads text from, in both themes",
    ),
    Claim(
        "SC-001",
        "and every boundary reaches 3:1, bar the board's registered exemptions",
        "console/tests/unit/design/contrast.test.ts",
        "reaches 3:1 on every boundary a viewer has to find, except the board's "
        "own registered exemptions",
    ),
    Claim(
        "SC-002",
        "every exported primitive appears in the gallery, by name",
        "console/tests/unit/gallery.test.tsx",
        "shows every primitive the library exports",
    ),
    Claim(
        "SC-002",
        "and the gallery shows nothing the library does not export",
        "console/tests/unit/gallery.test.tsx",
        "shows nothing the library does not export",
    ),
    Claim(
        "SC-003",
        "a hard-coded colour, spacing, radius or duration fails lint",
        "tests/contract/console/test_console_gate.py",
        "test_a_seeded_failure_fails_its_check_and_says_where",
    ),
    Claim(
        "SC-004",
        "the accessibility audit reports no violation over any gallery entry",
        "console/tests/unit/gallery.test.tsx",
        "the accessibility audit over every gallery entry",
    ),
    Claim(
        "SC-004",
        "and the audit itself has been shown a failure, so a clean run means something",
        "console/tests/unit/gallery.test.tsx",
        "finds an unnamed control, so a clean run means something",
    ),
    Claim(
        "SC-005",
        "no horizontal overflow at any declared width",
        "console/tests/e2e/gallery.spec.ts",
        "does not scroll sideways at ${String(width)}px",
    ),
    Claim(
        "SC-005",
        "and none at 200% zoom",
        "console/tests/e2e/gallery.spec.ts",
        "the gallery does not scroll sideways at 200% zoom",
    ),
    Claim(
        "SC-006",
        "switching theme changes no layout dimension",
        "console/tests/e2e/gallery.spec.ts",
        "switching theme changes no geometry, only colour",
    ),
    Claim(
        "FR-004",
        "the theme is applied before the first paint, not corrected after it",
        "console/tests/unit/design/theme.test.ts",
        "applies the stored choice before anything is painted",
    ),
    Claim(
        "FR-012",
        "an unknown status renders neutral with its raw text",
        "console/tests/unit/design/status.test.ts",
        "renders a status it has never heard of as neutral, with its own words",
    ),
    Claim(
        "FR-008",
        "no primitive shifts its layout between states",
        "console/tests/unit/components/action.test.tsx",
        "changes no geometry between states, so nothing moves under the pointer",
    ),
    Claim(
        "NFR-003",
        "reduced motion removes the animation rather than shortening it",
        "console/tests/e2e/gallery.spec.ts",
        "a viewer who asked for no motion gets none, rather than a shorter one",
    ),
    Claim(
        "NFR-002",
        "the gallery is the source the visual regression suite screenshots",
        "console/tests/visual/screens.spec.ts",
        "matches its baseline",
    ),
)


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: f"{claim.criterion}-{claim.test[:40]}")
def test_every_claim_has_the_test_it_names(claim: Claim) -> None:
    """The named test exists, in the named file."""
    module: Path = REPO_ROOT / claim.module
    assert module.is_file(), f"{claim.criterion}: {claim.module} does not exist"
    assert claim.test in module.read_text(encoding="utf-8"), (
        f"{claim.criterion} ({claim.claim}): {claim.module} no longer has a test called "
        f"{claim.test!r}. A criterion whose proof was renamed is a criterion nothing covers."
    )


def test_the_gallery_is_a_route_of_its_own_and_nothing_links_to_it() -> None:
    """It is the contract, not a page an operator should find during an incident."""
    gallery: Path = CONSOLE / "src" / "app" / "gallery" / "page.tsx"
    assert gallery.is_file(), "there is no gallery route"

    for source in (CONSOLE / "src").rglob("*.tsx"):
        if source.is_relative_to(CONSOLE / "src" / "app" / "gallery"):
            continue
        if source.is_relative_to(CONSOLE / "src" / "gallery"):
            continue
        assert "/gallery" not in source.read_text(encoding="utf-8"), (
            f"{source.name} links to the gallery; it is excluded from the console on purpose"
        )


def test_the_token_table_is_the_only_place_a_colour_is_written() -> None:
    """The mechanism the whole feature rests on, asserted rather than assumed."""
    exempt = {"tokens.ts", "css.ts"}
    for source in (CONSOLE / "src").rglob("*.ts*"):
        if source.name in exempt or source.name == "schema.ts":
            continue
        text = source.read_text(encoding="utf-8")
        for line in text.splitlines():
            assert "#" not in line or not _looks_like_a_colour(line), (
                f"{source.relative_to(CONSOLE)} writes a colour: {line.strip()}"
            )


def _looks_like_a_colour(line: str) -> bool:
    """Whether ``line`` contains a hex colour rather than a fragment or a comment."""
    import re

    return re.search(r"#[0-9a-fA-F]{6}\b", line) is not None


def test_the_lint_configuration_registers_the_rule_and_exempts_only_the_table() -> None:
    """Two files may write a value. Both are where values are declared."""
    configuration = (CONSOLE / "eslint.config.mjs").read_text(encoding="utf-8")

    assert "design/no-design-literals" in configuration
    assert "src/design/tokens.ts" in configuration
    assert "src/design/css.ts" in configuration


def test_the_stylesheets_are_linted_too() -> None:
    """ESLint parses JavaScript, and a stylesheet is the easiest place to hide one."""
    manifest: Any = json.loads((CONSOLE / "package.json").read_text(encoding="utf-8"))
    assert "check-css-literals" in manifest["scripts"]["lint"], (
        "the lint script does not cover the console's stylesheets"
    )


def test_the_budgets_are_in_the_gate_and_are_the_declared_ones() -> None:
    """A budget nobody measures is a wish; a budget with two numbers is neither."""
    assert "budget" in ORDER, "the gate does not measure the bundle budgets"

    measured = measure(CONSOLE)
    if measured is None:
        # No build on this machine. The icon set is source and is always there,
        # so the half that can be checked without a build still is.
        icons = icon_bytes(CONSOLE)
        assert icons is not None
        assert icons <= CONSOLE_ICON_BUDGET_BYTES
        return

    allowed = {budget.allowed for budget in measured}
    assert allowed == {CONSOLE_STYLESHEET_BUDGET_BYTES, CONSOLE_ICON_BUDGET_BYTES}
    for budget in measured:
        assert budget.within, budget.describe()


def test_every_design_reference_this_feature_owns_is_baselined() -> None:
    """The three references the design system implements are no longer pending."""
    registry: Any = json.loads((CONSOLE / "visual" / "screens.json").read_text(encoding="utf-8"))
    owned = {
        "01-tokens-colour.png",
        "02-tokens-scales.png",
        "07-states-empty-error.png",
        "08-theme-dark.png",
    }
    baselined = {
        str(entry["file"]) for entry in registry["mockups"] if entry["status"] == "baselined"
    }
    assert owned <= baselined, f"still pending: {sorted(owned - baselined)}"


def test_the_gallery_is_captured_at_every_declared_width_in_both_themes() -> None:
    """Three widths and two themes; a baseline that saw one proves nothing about five."""
    registry: Any = json.loads((CONSOLE / "visual" / "screens.json").read_text(encoding="utf-8"))
    captured = {
        (int(screen["viewport"]), str(screen["theme"]))
        for screen in registry["screens"]
        if str(screen["route"]) == "/gallery"
    }
    expected = {(width, theme) for width in (320, 768, 1440) for theme in ("light", "dark")}
    assert captured == expected, f"missing: {sorted(expected - captured)}"

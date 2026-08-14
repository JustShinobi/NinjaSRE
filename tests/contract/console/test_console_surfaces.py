"""What the console's data surfaces claim about the deployment, held against it.

Three kinds of claim live here, and none of them can be made in TypeScript.

The first is the **projected endpoints**. Several screens read paths the API
document does not declare yet — the estate inventory and continuous observation
are separate pieces of work — so the console names them in a closed list rather
than reaching for an escape hatch. That list is held against the mock data
plane's own catalogue below, which means it cannot drift and, more usefully,
**it has to shrink**: an endpoint that lands in the document moves to the
generated client, and this test fails until it comes out of the list.

The second is the **success criteria**, each against the named test that proves
it. A proof that is deleted or renamed fails here rather than quietly ceasing to
cover anything — the failure mode a list of claims in a document has and a list
of claims in a test does not.

The third is the pair of **structural** claims that are easiest to lose in a
rewrite: that exactly one component renders transcript events, and that no
configuration merge exists anywhere in the console.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from config.constants.console import NINJASRE_CONSOLE_CLOCK_ENV
from gateway.http.security.console_routes import CONSOLE_ROUTES
from gateway.http.security.gateway_routes import GATEWAY_ROUTES
from gateway.http.security.route_permissions import ROUTE_TABLE
from tools.console_toolchain import console_root
from tools.mockplane.endpoints import CONSOLE_ENDPOINTS, projected_endpoints

pytestmark = pytest.mark.contract

#: Where the console enumerates the endpoints nothing has generated a client for.
API_MODULE: Final = console_root() / "src" / "lib" / "api.ts"

#: The Node fixture server the unit suite and the visual capture both read.
FIXTURE_SERVER: Final = console_root() / "scripts" / "fixture-server.mjs"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _string_list(source: str, name: str) -> tuple[str, ...]:
    """Return the string literals of ``export const NAME = [...] as const``."""
    found = re.search(rf"export const {name} = \[(.*?)\] as const", source, re.DOTALL)
    assert found is not None, f"{name} is not declared"
    return tuple(re.findall(r"'([^']+)'", found.group(1)))


# --- The endpoints nothing has generated a client for ------------------------------


def test_every_projected_path_is_one_the_dataset_projects() -> None:
    """The console cannot invent an endpoint, even one nothing serves yet."""
    declared = _string_list(_source(API_MODULE), "PROJECTED_PATHS")
    catalogue = {endpoint.path for endpoint in projected_endpoints()}

    for path in declared:
        assert path in catalogue, (
            f"{path} is not an endpoint the mock data plane projects. The console may "
            "only read a path something has agreed to serve."
        )


def test_no_projected_path_is_one_the_document_already_declares() -> None:
    """The list shrinks: an endpoint that landed belongs to the generated client."""
    declared = set(_string_list(_source(API_MODULE), "PROJECTED_PATHS"))
    served = {endpoint.path for endpoint in CONSOLE_ENDPOINTS if endpoint.source.value == "gateway"}

    overlap = declared & served
    assert not overlap, (
        f"{sorted(overlap)} is served by the gateway now. Move it to the generated "
        "client and take it out of PROJECTED_PATHS — a second way to reach an "
        "endpoint is a second opinion about its shape."
    )


def test_the_fixture_server_answers_every_read_a_surface_makes() -> None:
    """A screen reading something the capture cannot answer is a blank screenshot."""
    table = re.search(
        r"SHELL_ENDPOINTS = Object\.freeze\(\{(.*?)\}\)", _source(FIXTURE_SERVER), re.DOTALL
    )
    assert table is not None, "the fixture server declares no endpoint table"

    served = set(dict(re.findall(r"'([^']+)':\s*'([^']+)'", table.group(1))))
    for path in _string_list(_source(API_MODULE), "PROJECTED_PATHS"):
        assert path in served, (
            f"{path} is read by a surface and the fixture server does not answer it; "
            "the unit suite and the visual capture would both see a 404."
        )


# --- Areas added after this file was first written, on the same claim -------------

#: Which gateway route each area reads, so its permission is the server's.
#:
#: ``catalogue`` named this dict's own area once, reaching ``/v1/capabilities``.
#: The menu reorganisation retired it as an area: its read half — browsing tools
#: and skills — moved to The agent's own Tools tab, and its write half — the
#: credential form and the verification control — became its own address,
#: ``integrations``, entered here on the permission ``GET /v1/integrations``
#: itself now requires (`gateway/http/security/gateway_routes.py`), which is
#: narrower than the read permission the old, merged screen held.
NEW_AREA_ROUTE: Final[dict[str, tuple[str, str]]] = {
    "integrations": ("GET", "/v1/integrations"),
    "administration": ("GET", "/identity/principals"),
}


@pytest.mark.parametrize("area", sorted(NEW_AREA_ROUTE))
def test_a_new_area_takes_the_permission_the_gateway_requires(area: str) -> None:
    """The console reads the permission the server enforces, by name."""
    source = _source(console_root() / "src" / "shell" / "routes.ts")
    declared = dict(
        re.findall(
            r"id:\s*'([a-z-]+)',.*?permission:\s*'([a-z.]+)',",
            source,
            re.DOTALL,
        )
    )
    method, path = NEW_AREA_ROUTE[area]
    table = ROUTE_TABLE.extended_with(GATEWAY_ROUTES).extended_with(CONSOLE_ROUTES)
    declaration = table.declaration_for(method, path)
    assert declaration.permission is not None, f"{method} {path} is public"

    assert declared[area] == declaration.permission.value, (
        f"{area} declares {declared[area]}, but the gateway requires "
        f"{declaration.permission.value} on {method} {path}"
    )


# --- The two structural claims ------------------------------------------------------


def _console_sources() -> tuple[Path, ...]:
    root = console_root() / "src"
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.suffix in {".ts", ".tsx"} and path.name != "schema.ts"
    )


def test_exactly_one_component_renders_transcript_events() -> None:
    """A live view and a history view are two obvious files, and one account of a run."""
    drawing = [
        path for path in _console_sources() if 'data-testid="transcript-event"' in _source(path)
    ]

    assert [path.name for path in drawing] == ["transcript-view.tsx"], (
        "a second component draws transcript entries; a run somebody watched and the "
        "same run read back tomorrow would stop being the same account of it"
    )


def test_every_screen_is_inside_the_untranslated_string_rule() -> None:
    """The screens are the most-read text in the console, so the rule has to reach them.

    The rule's ``files`` list is the whole of its scope: a directory absent from
    it is a directory where a literal sentence lints clean, and lints clean
    silently — nothing in the console fails, no catalogue key is missing, and
    the string is simply English for everybody. That is exactly the failure the
    rule exists to prevent, so the scope is asserted rather than remembered.
    """
    configuration = _source(console_root() / "eslint.config.mjs")
    scope = configuration[configuration.index("no-untranslated-strings rule") :]

    for pattern in ("'src/surfaces/**/*.tsx'", "'src/surfaces/**/*.ts'"):
        assert pattern in scope, (
            f"{pattern} is not in the untranslated-strings rule's file list, so every "
            f"sentence on every screen is outside the rule that makes the catalogue the "
            f"only source of user-visible text"
        )


def test_the_console_holds_no_configuration_merge() -> None:
    """The preview is the server's answer, and there is nowhere else it could come from."""
    merging = [
        path
        for path in _console_sources()
        if re.search(r"\bmergeConfig|\bresolveEffective|\bapplyPatch\b", _source(path))
    ]

    assert merging == [], (
        f"{[path.name for path in merging]} works out an effective configuration. A "
        "client-side merge that agrees with the server today disagrees with it after "
        "the next change to inheritance, and the operator previews one thing and saves "
        "another."
    )


def test_the_preview_handler_forwards_rather_than_deciding() -> None:
    """It posts the patch to the deployment and returns the answer verbatim."""
    handler = _source(console_root() / "src" / "app" / "api" / "preview" / "route.ts")

    assert "/preview" in handler, "the handler does not reach the deployment's preview"
    assert "NextResponse.json(previewed" in handler, (
        "the handler reshapes the deployment's answer, which is the second opinion it "
        "exists to avoid"
    )


def test_a_rejection_without_a_reason_is_refused_by_the_server_too() -> None:
    """The control on the screen is a courtesy; this is the rule."""
    handler = _source(console_root() / "src" / "app" / "api" / "decision" / "route.ts")

    assert "reasonRequired" in handler, "a reasonless rejection would reach the deployment"


# --- Each success criterion, against the test that proves it ------------------------


@dataclass(frozen=True, slots=True)
class Claim:
    """One thing this feature claims, and the named test that holds it."""

    criterion: str
    claim: str
    #: Relative to ``console/``.
    module: str
    #: A fragment of the test's own name, so a rename fails here.
    test: str


CLAIMS: Final[tuple[Claim, ...]] = (
    Claim(
        "SC-001",
        "every screen, against an empty deployment, names the next action",
        "tests/unit/surfaces/screens.test.tsx",
        "renders an empty state naming the next action",
    ),
    Claim(
        "SC-002",
        "ten thousand transcript events render inside the declared budget",
        "tests/unit/surfaces/transcript.test.tsx",
        "renders inside the declared budget",
    ),
    Claim(
        "SC-002",
        "and the cost does not grow with the length of the transcript",
        "tests/unit/surfaces/transcript.test.tsx",
        "draws the same number of entries as a hundred-event one",
    ),
    Claim(
        "SC-003",
        "one component serves both live and replayed runs, asserted structurally",
        "tests/unit/surfaces/transcript.test.tsx",
        "has exactly one component that draws a transcript entry",
    ),
    Claim(
        "SC-003",
        "and both readers produce the same vocabulary",
        "tests/unit/surfaces/transcript.test.tsx",
        "turns a live run into the same vocabulary",
    ),
    Claim(
        "SC-004",
        "for every role, every write control it cannot use is absent from every screen",
        "tests/unit/surfaces/role-matrix.test.tsx",
        "no control it cannot use is anywhere on any screen",
    ),
    Claim(
        "SC-005",
        "the preview is the deployment's answer, against a running gateway",
        "tests/e2e/surfaces.spec.ts",
        "the configuration preview is the deployment",
    ),
    Claim(
        "SC-005",
        "and the console renders that answer rather than working one out",
        "tests/unit/surfaces/config-editor.test.tsx",
        "renders the server",
    ),
    Claim(
        "SC-006",
        "a failing panel leaves the rest of its page functional",
        "tests/unit/surfaces/screens.test.tsx",
        "still renders its frame and names what failed",
    ),
    Claim(
        "SC-006",
        "and a panel that throws while rendering is contained to itself",
        "tests/unit/surfaces/panel.test.tsx",
        "shows its own error and its own retry while its sibling still renders",
    ),
    Claim(
        "SC-007",
        "every screen's filter and selection state round-trips through the URL",
        "tests/unit/surfaces/url-state.test.ts",
        "round-trips every filter, the sort, the page and the selection",
    ),
    Claim(
        "SC-007",
        "and a filtered view survives a reload in a browser",
        "tests/e2e/surfaces.spec.ts",
        "survives being reloaded and shared",
    ),
    Claim(
        "SC-008",
        "five hundred configuration nodes render within budget, every node present",
        "tests/unit/surfaces/tree.test.tsx",
        "are all present, and render inside the declared budget",
    ),
    Claim(
        "NFR-004",
        "a masked identifier is restored by the server and never by the console",
        "tests/unit/surfaces/masking.test.tsx",
        "is rendered as the server spelled it, with no branch in between",
    ),
)


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: f"{claim.criterion}: {claim.claim}")
def test_each_success_criterion_is_proven_by_a_named_test(claim: Claim) -> None:
    """The proof exists, in the file it is supposed to be in, under that name."""
    module = console_root() / claim.module
    assert module.is_file(), f"{claim.criterion} names {claim.module}, which is not there"
    assert claim.test in _source(module), (
        f"{claim.criterion} ({claim.claim}) names a test containing {claim.test!r} in "
        f"{claim.module}, and there is none"
    )


def test_every_criterion_the_specification_declares_is_claimed() -> None:
    """Eight criteria, none of them quietly dropped from the list above."""
    declared = {claim.criterion for claim in CLAIMS if claim.criterion.startswith("SC-")}
    assert declared == {f"SC-{number:03d}" for number in range(1, 9)}


def test_the_console_and_this_tier_agree_about_the_fixed_clock() -> None:
    """One name, in two files, or the capture reads the wall clock and drifts."""
    source = _source(console_root() / "src" / "surfaces" / "context.ts")
    declared = re.search(r"export const CLOCK_ENV = '([^']+)'", source)
    assert declared is not None, "the console declares no fixed clock"

    assert declared.group(1) == NINJASRE_CONSOLE_CLOCK_ENV
    assert NINJASRE_CONSOLE_CLOCK_ENV in _source(console_root() / "scripts" / "visual.mjs"), (
        "the visual capture does not fix the clock, so a baseline fails on the hour"
    )


def test_the_console_and_the_platform_agree_about_which_levels_only_read() -> None:
    """The read/write split the agent screen groups by is the platform's own scale.

    The console has to decide which side of the risk line a tool sits on, and the
    scale is Python's. A list in TypeScript that drifted would put a write in the
    read column — which is the one direction this must never be wrong in, because
    the column is what an operator scans before deciding what this thing may do
    unattended. So the console names the read-only levels once and this holds
    them against the scale: a level added in Python fails in Python.
    """
    from config.constants.security import SIDE_EFFECT_LEVELS, SIDE_EFFECT_READ

    source = _source(console_root() / "src" / "surfaces" / "capability-rows.ts")
    declared = re.search(r"READ_ONLY_LEVELS: readonly string\[\] = \[([^\]]*)\]", source)
    assert declared is not None, "the console does not declare which levels only read"
    named = tuple(
        entry.strip().strip("'") for entry in declared.group(1).split(",") if entry.strip()
    )

    assert named[0] == SIDE_EFFECT_READ
    for level in named:
        assert level in SIDE_EFFECT_LEVELS, f"{level!r} is not a level this platform has"
    # Everything else writes, and the console treats an unknown level as a write,
    # which is the same default the platform takes for an undeclared capability.
    assert set(named) < set(SIDE_EFFECT_LEVELS)

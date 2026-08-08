"""What the console's shell claims about the server, held against the server.

The console is TypeScript and cannot import a Python module, which is exactly
why these tests exist. Four things in the shell are *restatements* of something
the platform already decides — the permission each area needs, the roles a role
matrix walks, the session's own names and durations, and the endpoints a fixture
server answers. Each of them could drift silently, and each of them would drift
into the same failure: a console that is confidently wrong about the deployment
it is talking to.

So each is read out of the console's source and compared against the authority
here. A permission that moved fails in Python rather than by showing somebody a
page they cannot load.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from config.constants.console import (
    CONSOLE_FIRST_PAINT_BUDGET_MS,
    CONSOLE_LOCALE_COOKIE,
    CONSOLE_LOCALES,
    CONSOLE_ROUTE_TRANSITION_BUDGET_MS,
    CONSOLE_SESSION_COOKIE,
    CONSOLE_SESSION_EXPIRY_COOKIE,
    CONSOLE_SESSION_LIFETIME_SECONDS,
    CONSOLE_SESSION_WARNING_SECONDS,
    CONSOLE_SHELL_READ_TIMEOUT_MS,
    CONSOLE_SIDEBAR_BREAKPOINT_PX,
    CONSOLE_SIDEBAR_WIDTH_PX,
    CONSOLE_SIGN_IN_PATH,
    CONSOLE_TOPBAR_HEIGHT_PX,
)
from gateway.http.security.console_routes import CONSOLE_ROUTES
from gateway.http.security.gateway_routes import GATEWAY_ROUTES
from gateway.http.security.route_permissions import ROUTE_TABLE
from platform.identity.permissions import ROLE_ORDER, Permission, permissions_for
from tools.console_roles import drifted, roles_path
from tools.console_toolchain import console_root
from tools.mockplane.endpoints import CONSOLE_ENDPOINTS

pytestmark = pytest.mark.contract

#: The console's route manifest, which is the only list of what routes exist.
ROUTES_MODULE: Final = console_root() / "src" / "shell" / "routes.ts"

#: Where the console mirrors the session's names and durations.
COOKIES_MODULE: Final = console_root() / "src" / "shell" / ".." / "session" / "cookies.ts"

#: Where the shell's two fixed measurements and its breakpoint are declared.
TOKENS_MODULE: Final = console_root() / "src" / "design" / "tokens.ts"

#: The Node fixture server the visual capture serves the dataset with.
FIXTURE_SERVER: Final = console_root() / "scripts" / "fixture-server.mjs"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def declared_areas() -> tuple[tuple[str, str, str], ...]:
    """Return ``(id, path, permission)`` for every area the console declares."""
    source = _source(ROUTES_MODULE)
    found: list[tuple[str, str, str]] = []
    for block in re.finditer(
        r"\{\s*id:\s*'([a-z-]+)',\s*path:\s*'([^']+)',.*?permission:\s*'([a-z.]+)',",
        source,
        re.DOTALL,
    ):
        found.append((block.group(1), block.group(2), block.group(3)))
    return tuple(found)


def _string_constant(source: str, name: str) -> str:
    found = re.search(rf"export const {name} = '([^']*)'", source)
    assert found is not None, f"{name} is not declared"
    return found.group(1)


def _number_constant(source: str, name: str) -> float:
    found = re.search(rf"export const {name} = ([0-9_]+)", source)
    assert found is not None, f"{name} is not declared"
    return float(found.group(1).replace("_", ""))


# --- The manifest is a manifest ---------------------------------------------------


def test_the_console_declares_at_least_the_areas_the_design_draws() -> None:
    """Twelve areas in four groups, which is what the reference navigation shows."""
    areas = declared_areas()
    assert len(areas) >= 12, areas
    assert len({identifier for identifier, _, _ in areas}) == len(areas)
    assert len({path for _, path, _ in areas}) == len(areas)


def test_every_declared_permission_is_one_the_platform_has() -> None:
    """The console names a permission; it never invents one."""
    catalogue = {permission.value for permission in Permission}
    for identifier, _, permission in declared_areas():
        assert permission in catalogue, f"{identifier} names {permission}, which does not exist"


#: Which route each area reads, for the areas whose data the gateway already
#: serves. The four that are missing — incidents, resources, detectors and
#: autonomy — are projections with no gateway row yet; the permission-catalogue
#: test above is what holds those, and this table gains a row for each of them
#: as the endpoint that serves it lands.
AREA_ROUTE: Final[dict[str, tuple[str, str]]] = {
    "dashboard": ("GET", "/v1/runs"),
    "runs": ("GET", "/v1/runs"),
    "approvals": ("GET", "/v1/approvals"),
    "topology": ("GET", "/v1/topology/{node_id}"),
    "memory": ("GET", "/v1/memory/stats"),
    "knowledge": ("GET", "/v1/knowledge/documents"),
    "configuration": ("GET", "/v1/config"),
    "audit": ("GET", "/audit/events"),
}


def _server_permission(method: str, path: str) -> str:
    """Return the permission the gateway requires on one route.

    Composed the way the application composes it, so this reads the same table a
    request is checked against rather than a copy of one.
    """
    table = ROUTE_TABLE.extended_with(GATEWAY_ROUTES).extended_with(CONSOLE_ROUTES)
    declaration = table.declaration_for(method, path)
    assert declaration.permission is not None, f"{method} {path} is public"
    return declaration.permission.value


@pytest.mark.parametrize("area", sorted(AREA_ROUTE))
def test_an_area_takes_the_permission_the_gateway_requires_of_its_data(area: str) -> None:
    """The console reads the permission the server enforces, by name."""
    declared = {identifier: permission for identifier, _, permission in declared_areas()}
    method, path = AREA_ROUTE[area]

    assert declared[area] == _server_permission(method, path), (
        f"{area} declares {declared[area]}, but the gateway requires "
        f"{_server_permission(method, path)} on {method} {path}"
    )


def test_the_role_matrix_can_tell_two_roles_apart() -> None:
    """The least privileged role reaches strictly fewer areas than the most.

    Without this the matrix could pass against a manifest where every area needs
    the same permission, which would prove nothing about presence at all.
    """
    areas = declared_areas()
    least, most = ROLE_ORDER[0], ROLE_ORDER[-1]
    reachable = {
        role: sum(
            1
            for _, _, permission in areas
            if permission in {held.value for held in permissions_for(role)}
        )
        for role in (least, most)
    }
    assert reachable[least] < reachable[most], reachable


# --- The generated role catalogue -------------------------------------------------


def test_the_role_catalogue_the_console_reads_is_the_one_the_platform_generates() -> None:
    """A hand-edited catalogue is a role matrix proving something about nothing."""
    assert not drifted(), (
        f"{roles_path()} is not what the permission catalogue generates; "
        "run `python -m tools.console_roles write`"
    )


def test_the_role_catalogue_carries_every_role_and_every_permission() -> None:
    """It is the whole catalogue rather than a subset somebody chose."""
    document = json.loads(roles_path().read_text(encoding="utf-8"))

    assert document["order"] == [role.value for role in ROLE_ORDER]
    assert set(document["permissions"]) == {permission.value for permission in Permission}
    for role in ROLE_ORDER:
        assert set(document["roles"][role.value]) == {
            permission.value for permission in permissions_for(role)
        }


# --- The session's own names ------------------------------------------------------


def test_the_console_and_this_tier_agree_about_the_session() -> None:
    """Two files hold these names; a change to one without the other fails here."""
    source = _source(COOKIES_MODULE)

    assert _string_constant(source, "SESSION_COOKIE") == CONSOLE_SESSION_COOKIE
    assert _string_constant(source, "SESSION_EXPIRY_COOKIE") == CONSOLE_SESSION_EXPIRY_COOKIE
    assert _string_constant(source, "LOCALE_COOKIE") == CONSOLE_LOCALE_COOKIE
    assert _string_constant(source, "SIGN_IN_PATH") == CONSOLE_SIGN_IN_PATH
    assert _number_constant(source, "SESSION_LIFETIME_SECONDS") == CONSOLE_SESSION_LIFETIME_SECONDS
    assert _number_constant(source, "SESSION_WARNING_SECONDS") == CONSOLE_SESSION_WARNING_SECONDS


def test_the_console_and_this_tier_agree_about_the_shell_geometry() -> None:
    """The sidebar's width, the utility bar's height, and where it collapses."""
    source = _source(TOKENS_MODULE)
    shell = re.search(r"export const SHELL = \{(.*?)\}", source, re.DOTALL)
    assert shell is not None, "the token table declares no shell geometry"

    assert f"sidebar: {CONSOLE_SIDEBAR_WIDTH_PX}" in shell.group(1)
    assert f"topbar: {CONSOLE_TOPBAR_HEIGHT_PX}" in shell.group(1)
    assert _number_constant(source, "SIDEBAR_BREAKPOINT") == CONSOLE_SIDEBAR_BREAKPOINT_PX


def test_the_shell_gives_its_own_reads_the_deadline_this_tier_declares() -> None:
    """A frame that waits on a notification count is a frame a slow API delays."""
    source = _source(console_root() / "src" / "shell" / "load.ts")
    assert _number_constant(source, "SHELL_READ_TIMEOUT_MS") == CONSOLE_SHELL_READ_TIMEOUT_MS


def test_the_console_carries_the_locales_this_tier_declares() -> None:
    """A locale added on one side and not the other is a catalogue nobody checks."""
    source = _source(console_root() / "src" / "i18n" / "messages.ts")
    declared = re.search(r"export const LOCALES = \[(.*?)\] as const", source, re.DOTALL)
    assert declared is not None

    found = tuple(re.findall(r"'([^']+)'", declared.group(1)))
    assert found == CONSOLE_LOCALES


def test_the_budgets_the_browser_suite_reads_are_the_ones_declared_here() -> None:
    """The suite parses this module; these assertions are that it can."""
    source = (
        Path(__file__).resolve().parents[3] / "config" / "constants" / "console.py"
    ).read_text(encoding="utf-8")

    assert f"CONSOLE_FIRST_PAINT_BUDGET_MS: Final = {CONSOLE_FIRST_PAINT_BUDGET_MS}" in source
    assert (
        f"CONSOLE_ROUTE_TRANSITION_BUDGET_MS: Final = {CONSOLE_ROUTE_TRANSITION_BUDGET_MS}"
        in source
    )


# --- The fixture server the visual capture uses -----------------------------------


def test_the_fixture_server_answers_endpoints_the_dataset_actually_has() -> None:
    """Its little table is held against the mock plane's own catalogue."""
    source = _source(FIXTURE_SERVER)
    table = re.search(r"SHELL_ENDPOINTS = Object\.freeze\(\{(.*?)\}\)", source, re.DOTALL)
    assert table is not None, "the fixture server declares no endpoint table"

    declared = dict(re.findall(r"'([^']+)':\s*'([^']+)'", table.group(1)))
    by_path = {endpoint.path: endpoint.slug for endpoint in CONSOLE_ENDPOINTS}
    for path, slug in declared.items():
        assert path in by_path, f"{path} is not an endpoint the dataset covers"
        assert by_path[path] == slug, f"{path} is fixture {by_path[path]}, not {slug}"


# --- Each success criterion, against the test that proves it ----------------------


@dataclass(frozen=True, slots=True)
class Claim:
    """One thing this feature claims, and the named test that holds it."""

    criterion: str
    claim: str
    #: Relative to ``console/``.
    module: str
    #: A fragment of the test's own name, so a rename fails here rather than
    #: quietly ceasing to cover anything.
    test: str


#: The shell's success criteria. A proof that was deleted or renamed fails here,
#: which is the failure mode a list of claims in a document does not have.
CLAIMS: Final[tuple[Claim, ...]] = (
    Claim(
        "SC-001",
        "every route, opened unauthenticated, renders the sign-in and nothing else",
        "tests/unit/session/guard.test.ts",
        "is sent to the sign-in from",
    ),
    Claim(
        "SC-001",
        "and the same, in a browser, against the built artefact",
        "tests/e2e/shell.spec.ts",
        "sees the sign-in and nothing else at",
    ),
    Claim(
        "SC-002",
        "a 401 on three concurrent calls ends the session once and prompts once",
        "tests/unit/session/controller.test.ts",
        "produce exactly one session ending and one prompt",
    ),
    Claim(
        "SC-003",
        "for every role, every nav entry it cannot use is absent from the DOM",
        "tests/unit/shell/role-matrix.test.tsx",
        "is present only if held",
    ),
    Claim(
        "SC-003",
        "and every shell control it cannot use, likewise",
        "tests/unit/shell/role-matrix.test.tsx",
        "is present only with",
    ),
    Claim(
        "SC-004",
        "a deep link to every route renders that route cold, with its title",
        "tests/unit/shell/route-files.test.tsx",
        "renders cold, with its own title",
    ),
    Claim(
        "SC-004",
        "and the same in a browser",
        "tests/e2e/shell.spec.ts",
        "cold, with its own title",
    ),
    Claim(
        "SC-005",
        "the palette is fully operable without a pointer",
        "tests/unit/shell/palette.test.tsx",
        "the palette, from the keyboard alone",
    ),
    Claim(
        "SC-006",
        "the catalogue is complete for every supported locale, naming any gap",
        "tests/unit/i18n/catalogue.test.ts",
        "carries every key in every locale, and names any that is missing",
    ),
    Claim(
        "SC-007",
        "the first-paint budget holds",
        "tests/e2e/budgets.spec.ts",
        "paints its frame inside the first-paint budget",
    ),
    Claim(
        "SC-007",
        "the route-transition budget holds",
        "tests/e2e/budgets.spec.ts",
        "lands inside the transition budget",
    ),
)


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: f"{claim.criterion}: {claim.claim}")
def test_each_success_criterion_is_proven_by_a_named_test(claim: Claim) -> None:
    """The proof exists, in the file it is supposed to be in, under that name."""
    module = console_root() / claim.module
    assert module.is_file(), f"{claim.criterion} names {claim.module}, which is not there"
    assert claim.test in _source(module), (
        f"{claim.criterion} ({claim.claim}) names a test containing "
        f"{claim.test!r} in {claim.module}, and there is none"
    )


def test_every_criterion_the_specification_declares_is_claimed() -> None:
    """Seven criteria, none of them quietly dropped from the list above."""
    assert {claim.criterion for claim in CLAIMS} == {f"SC-{number:03d}" for number in range(1, 8)}

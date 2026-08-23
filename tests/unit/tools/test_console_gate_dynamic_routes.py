"""The dynamic-routes check: pure logic, proved against a synthetic build tree.

Deliberately not driven through a real ``next build`` — that is what
``tests/contract/console/test_console_gate.py`` is for, and it costs minutes a
contributor iterating on this check should not have to pay. What is proved
here is the check's own reasoning: how it derives a shell route from a
``page.tsx`` path, how it reads the manifest Next.js itself writes, and how
the two combine into a pass or a named failure — against a ``tmp_path`` tree
this file builds by hand, never against the console's own checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.console_gate import _prerendered_paths, _route_from_page, _shell_routes, dynamic_routes

pytestmark = pytest.mark.unit


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _manifest(console: Path, *, routes: dict[str, object], dynamic: dict[str, object]) -> None:
    (console / ".next").mkdir(parents=True, exist_ok=True)
    (console / ".next" / "prerender-manifest.json").write_text(
        json.dumps({"version": 4, "routes": routes, "dynamicRoutes": dynamic}),
        encoding="utf-8",
    )


# --- Deriving a route from a page.tsx path -----------------------------------


def test_a_top_level_page_under_the_shell_group_is_the_bare_route() -> None:
    app_root = Path("src/app")
    page = app_root / "(shell)" / "incidents" / "page.tsx"
    assert _route_from_page(app_root, page) == "/incidents"


def test_the_shell_groups_own_index_page_is_the_root_route() -> None:
    app_root = Path("src/app")
    page = app_root / "(shell)" / "page.tsx"
    assert _route_from_page(app_root, page) == "/"


def test_a_dynamic_segment_keeps_its_bracket_spelling() -> None:
    app_root = Path("src/app")
    page = app_root / "(shell)" / "incidents" / "[incidentId]" / "page.tsx"
    assert _route_from_page(app_root, page) == "/incidents/[incidentId]"


def test_a_route_group_outside_the_shell_is_dropped_the_same_way() -> None:
    app_root = Path("src/app")
    page = app_root / "(other)" / "settings" / "page.tsx"
    assert _route_from_page(app_root, page) == "/settings"


# --- Enumerating the shell's own routes ---------------------------------------


def test_every_page_under_the_shell_group_is_collected(tmp_path: Path) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "page.tsx")
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "[incidentId]" / "page.tsx")
    assert _shell_routes(console) == ("/", "/incidents", "/incidents/[incidentId]")


def test_a_page_outside_the_shell_group_is_not_collected(tmp_path: Path) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _touch(console / "src" / "app" / "gallery" / "page.tsx")
    assert _shell_routes(console) == ("/incidents",)


# --- Reading the manifest -----------------------------------------------------


def test_prerendered_paths_is_the_union_of_static_and_dynamic_route_entries(
    tmp_path: Path,
) -> None:
    _manifest(
        tmp_path,
        routes={"/gallery": {}, "/icon.svg": {}},
        dynamic={"/blog/[slug]": {}},
    )
    assert _prerendered_paths(tmp_path / ".next") == frozenset(
        {"/gallery", "/icon.svg", "/blog/[slug]"}
    )


def test_prerendered_paths_is_empty_when_there_is_no_manifest_at_all(tmp_path: Path) -> None:
    assert _prerendered_paths(tmp_path / ".next") == frozenset()


# --- The check itself ----------------------------------------------------------


def test_the_check_skips_when_there_is_no_build_to_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = dynamic_routes(tmp_path)
    assert status == 0
    assert "no console build" in capsys.readouterr().err.lower()


def test_the_check_passes_when_no_shell_route_is_prerendered(tmp_path: Path) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _manifest(console, routes={"/gallery": {}}, dynamic={})
    assert dynamic_routes(console) == 0


def test_the_check_fails_and_names_a_shell_route_that_is_prerendered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _touch(console / "src" / "app" / "(shell)" / "runs" / "page.tsx")
    _manifest(console, routes={"/incidents": {}}, dynamic={})
    status = dynamic_routes(console)
    assert status == 1
    assert "/incidents" in capsys.readouterr().err


def test_the_check_names_every_prerendered_shell_route_not_just_the_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _touch(console / "src" / "app" / "(shell)" / "runs" / "page.tsx")
    _manifest(console, routes={"/incidents": {}, "/runs": {}}, dynamic={})
    status = dynamic_routes(console)
    assert status == 1
    error = capsys.readouterr().err
    assert "/incidents" in error
    assert "/runs" in error


def test_the_check_ignores_a_prerendered_route_outside_the_shell(tmp_path: Path) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _touch(console / "src" / "app" / "gallery" / "page.tsx")
    _manifest(console, routes={"/gallery": {}}, dynamic={})
    assert dynamic_routes(console) == 0


def test_a_prerendered_dynamic_segment_route_is_caught_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "[incidentId]" / "page.tsx")
    _manifest(console, routes={}, dynamic={"/incidents/[incidentId]": {}})
    status = dynamic_routes(console)
    assert status == 1
    assert "/incidents/[incidentId]" in capsys.readouterr().err


def test_reverting_a_route_to_prerendered_and_back_flips_the_check_both_ways(
    tmp_path: Path,
) -> None:
    """The regression proof: this is not a check that only ever passes."""
    console = tmp_path
    _touch(console / "src" / "app" / "(shell)" / "incidents" / "page.tsx")
    _manifest(console, routes={}, dynamic={})
    assert dynamic_routes(console) == 0

    _manifest(console, routes={"/incidents": {}}, dynamic={})
    assert dynamic_routes(console) == 1

    _manifest(console, routes={}, dynamic={})
    assert dynamic_routes(console) == 0

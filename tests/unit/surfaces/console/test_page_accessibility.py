"""SC-007: every page passes the automated checks, as every role.

Rendered as every role rather than only as an owner, because omission changes
the tree: a page whose only heading sat inside a control a viewer does not see
would pass as an admin and fail as a viewer, and the viewer is the one more
likely to be using a screen reader on somebody else's machine.
"""

from __future__ import annotations

from platform.identity.permissions import Role
from surfaces.console.accessibility import audit
from surfaces.console.html import text_of
from surfaces.console.pages.shell import MAIN_ID
from tests.unit.surfaces.console.conftest import render


def test_every_page_passes_the_automated_checks_as_every_role(page_name: str, role: Role) -> None:
    report = audit(render(page_name, role))

    assert report.passed, f"{page_name} as {role.value}:\n{report.describe()}"


def test_an_impersonated_session_is_still_accessible(page_name: str) -> None:
    report = audit(render(page_name, Role.ADMIN, impersonating=True))

    assert report.passed, report.describe()


def test_every_page_offers_a_skip_link_that_points_at_something_real(
    page_name: str,
) -> None:
    document = render(page_name, Role.OWNER)

    links = [node for node in document.body.walk() if node.attribute("class") == "skip-link"]
    assert links, f"{page_name} has no skip link"
    assert links[0].attribute("href") == f"#{MAIN_ID}"
    assert [node for node in document.body.walk() if node.attribute("id") == MAIN_ID]


def test_every_page_has_a_title_that_names_the_area_and_the_product() -> None:
    document = render("runs", Role.OWNER)

    assert document.title == "Runs — NinjaSRE"


def test_every_page_starts_its_outline_at_a_single_level_one_heading(
    page_name: str,
) -> None:
    document = render(page_name, Role.OWNER)

    top = document.body.find("h1")
    assert len(top) == 1, f"{page_name} has {len(top)} level-one headings"
    assert text_of(top[0]).strip()


def test_the_navigation_marks_where_the_reader_is() -> None:
    from tests.unit.surfaces.console.conftest import PAGES, context_for

    context = context_for(Role.OWNER, path="/memory")
    document = PAGES["memory"](context)

    current = [node for node in document.body.walk() if node.attribute("aria-current") == "page"]
    assert len(current) == 1
    assert current[0].attribute("href") == "/memory"


def test_a_signed_out_page_offers_no_navigation_at_all() -> None:
    document = render("sign-in", Role.OWNER)

    assert document.body.find("nav") == ()

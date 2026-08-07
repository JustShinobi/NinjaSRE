"""The frame every page sits in, and the widgets every page builds from.

Three things live here because they must be identical everywhere and are the
easiest to get subtly different per page: the navigation, the impersonation
banner, and the accessible spellings of a table, a field, and a card.

The impersonation banner is the one with teeth. FR-024 asks for it to be
unmistakable *throughout* the session, so it is emitted by ``page`` rather than
by each area — there is no page that can forget it, because no page renders its
own frame.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from platform.identity.permissions import Permission
from surfaces.console.html import Child, Document, Element, element, fragment
from surfaces.console.i18n import ENGLISH, Catalogue
from surfaces.console.permissions import Viewer
from surfaces.console.theme import stylesheet

#: The id the skip link jumps to. One constant, because a skip link pointing at
#: an id nothing carries is worse than no skip link: it announces a shortcut and
#: then does nothing.
MAIN_ID: Final = "main-content"


@dataclass(frozen=True, slots=True)
class Area:
    """One top-level destination, and what a principal needs to see it."""

    path: str
    label_key: str
    permission: Permission


#: The console's information architecture, in the order it is navigated. Each
#: area names the permission its own data needs — so a principal who cannot read
#: configuration is not offered a configuration tab that would 403.
AREAS: Final[tuple[Area, ...]] = (
    Area("/runs", "nav.runs", Permission.INVESTIGATION_READ),
    Area("/interactions", "nav.interactions", Permission.APPROVAL_READ),
    Area("/memory", "nav.memory", Permission.MEMORY_READ),
    Area("/knowledge", "nav.knowledge", Permission.KNOWLEDGE_READ),
    Area("/config", "nav.config", Permission.CONFIG_READ),
    Area("/catalogue", "nav.catalogue", Permission.CONFIG_READ),
    Area("/admin", "nav.admin", Permission.IDENTITY_READ),
    Area("/onboarding", "nav.onboarding", Permission.CONFIG_WRITE),
)


@dataclass(frozen=True, slots=True)
class PageContext:
    """Who is looking at a page, and where they are.

    Carries a ``Viewer`` and never a ``Session``: a page builder has no use for
    a bearer token and giving it one would be one more place a token could be
    rendered.
    """

    viewer: Viewer = field(default_factory=Viewer)
    path: str = "/runs"
    catalogue: Catalogue = ENGLISH
    #: Something to say at the top of the page — a session about to expire, a
    #: stream that reconnected, a decision that landed from somewhere else.
    notice: str = ""

    def text(self, key: str, **values: object) -> str:
        """Return the string ``key`` names, in this context's locale."""
        return self.catalogue.text(key, **values)

    def areas(self) -> tuple[Area, ...]:
        """Return the areas this viewer may reach.

        Omission again: an area whose data the viewer cannot read is absent
        rather than shown and refused. A tab that 403s is a tab that tells
        somebody the deployment has a thing they are not allowed to have.
        """
        return tuple(area for area in AREAS if self.viewer.holds(area.permission))


def page(context: PageContext, *, title_key: str, body: Element) -> Document:
    """Return the whole page: skip link, banners, navigation, and ``body``.

    Every page goes through here. That is what makes the impersonation banner,
    the language attribute, the skip link, and the single ``<main>`` landmark
    properties of the console rather than of whoever wrote the page.
    """
    return Document(
        title=f"{context.text(title_key)} — {context.text('app.name')}",
        stylesheet=stylesheet(),
        body=element(
            "div",
            element(
                "a", context.text("app.skip_to_content"), href=f"#{MAIN_ID}", class_="skip-link"
            ),
            _impersonation_banner(context),
            _notice(context),
            _navigation(context),
            element("main", body, id=MAIN_ID),
            class_="shell",
        ),
    )


def signed_out_page(context: PageContext, *, title_key: str, body: Element) -> Document:
    """Return a page for somebody who is not signed in.

    No navigation at all — acceptance scenario 1 says an unauthenticated visitor
    sees the sign-in and nothing else, and a navigation bar listing the areas of
    the deployment is a description of the deployment.
    """
    return Document(
        title=f"{context.text(title_key)} — {context.text('app.name')}",
        stylesheet=stylesheet(),
        body=element(
            "div",
            element(
                "a", context.text("app.skip_to_content"), href=f"#{MAIN_ID}", class_="skip-link"
            ),
            _notice(context),
            element("main", body, id=MAIN_ID),
            class_="shell",
        ),
    )


def _impersonation_banner(context: PageContext) -> Element | None:
    """Return the banner an impersonating session carries on every page (FR-024)."""
    if not context.viewer.impersonating:
        return None
    return element(
        "div",
        element(
            "p",
            context.text("auth.impersonating", principal=context.viewer.principal_id),
        ),
        element("a", context.text("auth.impersonation_end"), href="/impersonation/end"),
        class_="banner banner--impersonation",
        role="status",
        data_impersonation="true",
    )


def _notice(context: PageContext) -> Element | None:
    """Return the page's notice, announced politely rather than interrupting."""
    if not context.notice:
        return None
    return element("p", context.notice, class_="notice", role="status")


def _navigation(context: PageContext) -> Element:
    """Return the area navigation, marking where the reader is."""
    return element(
        "nav",
        element(
            "ul",
            *[
                element(
                    "li",
                    element(
                        "a",
                        context.text(area.label_key),
                        href=area.path,
                        aria_current="page" if context.path.startswith(area.path) else None,
                    ),
                )
                for area in context.areas()
            ],
        ),
        class_="shell__nav",
        aria_label=context.text("nav.label"),
    )


# --- Widgets ------------------------------------------------------------------


def card(*children: Child, danger: bool = False, **attributes: str | bool | None) -> Element:
    """Return a bounded block of related content."""
    return element(
        "article",
        *children,
        class_="card card--danger" if danger else "card",
        **attributes,
    )


def form_field(
    *,
    identifier: str,
    label: str,
    name: str = "",
    kind: str = "text",
    value: str = "",
    help_text: str = "",
    required: bool = False,
    autocomplete: str | None = None,
) -> Element:
    """Return a labelled form control, with the label actually associated with it.

    The one spelling of a form field in the console. A field written by hand is
    a field somebody wrote without a ``for``, and the accessibility harness
    would catch it — but only on the page that shipped it.
    """
    described_by = f"{identifier}-help" if help_text else None
    return element(
        "div",
        element("label", label, for_=identifier),
        element(
            "textarea" if kind == "textarea" else "input",
            "" if kind == "textarea" else None,
            id=identifier,
            name=name or identifier,
            type=None if kind == "textarea" else kind,
            value=value if kind != "textarea" else None,
            required=required,
            autocomplete=autocomplete,
            aria_describedby=described_by,
        ),
        element("p", help_text, id=described_by, class_="muted") if help_text else None,
        class_="field",
    )


def table(
    *,
    caption: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Child]],
    empty: str,
    **attributes: str | bool | None,
) -> Element:
    """Return a data table, or the empty state when there is nothing in it.

    ``data-label`` on every cell is what makes the responsive stacking on a
    phone (FR-028) readable: once the header row is off-screen, a bare value in
    a stacked list means nothing.
    """
    if not rows:
        return element("p", empty, class_="muted", **attributes)
    return element(
        "table",
        element("caption", caption),
        element(
            "thead",
            element("tr", *[element("th", heading, scope="col") for heading in columns]),
        ),
        element(
            "tbody",
            *[
                element(
                    "tr",
                    *[
                        element(
                            "td",
                            cell,
                            data_label=columns[index] if index < len(columns) else None,
                        )
                        for index, cell in enumerate(row)
                    ],
                )
                for row in rows
            ],
        ),
        **attributes,
    )


def definitions(pairs: Sequence[tuple[str, Child]], **attributes: str | bool | None) -> Element:
    """Return a description list, which is what most of this console's detail is."""
    return element(
        "dl",
        *[fragment(element("dt", term), element("dd", description)) for term, description in pairs],
        **attributes,
    )


def heading(level: int, content: Child, **attributes: str | bool | None) -> Element:
    """Return a heading at ``level``, so an outline is built rather than styled."""
    return element(f"h{max(1, min(level, 6))}", content, **attributes)


def form(
    *children: Child,
    action: str,
    method: str = "post",
    label: str,
    **attributes: str | bool | None,
) -> Element:
    """Return a form with an accessible name, which a landmark needs to be useful."""
    return element("form", *children, action=action, method=method, aria_label=label, **attributes)


def value_or_dash(context: PageContext, value: object) -> str:
    """Return ``value`` as text, or an em dash when there is nothing to show."""
    rendered = "" if value is None else str(value)
    return rendered if rendered.strip() else context.text("common.none")


def badge(text_content: str, *, kind: str = "") -> Element:
    """Return a small status marker that also says what it means in words.

    Never colour alone: the class is styling, the text is the information, and a
    reader who cannot tell the colours apart loses nothing.
    """
    return element("span", text_content, class_=f"badge badge--{kind}" if kind else "badge")


__all__ = [
    "AREAS",
    "MAIN_ID",
    "Area",
    "PageContext",
    "badge",
    "card",
    "definitions",
    "form_field",
    "form",
    "heading",
    "page",
    "signed_out_page",
    "table",
    "value_or_dash",
]

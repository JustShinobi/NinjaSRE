"""Automated WCAG 2.1 AA checks, run over the page tree rather than a screenshot.

Automated checking finds roughly a third to a half of WCAG failures. That is not
a reason to skip it — it is a reason to be precise about which third. What is
checkable from structure alone is exactly what is checked here, each rule naming
the success criterion it comes from, and the rest stays a human's job rather
than being asserted falsely by a green test.

Every rule is a *structural* one: a control with no accessible name, an image
with no alternative, a heading level skipped, a form field with no label, a page
with two ``<main>`` elements or none. Those are the failures that make a screen
reader unusable, they are the ones a developer introduces without noticing, and
they are all visible in the tree the console builds.

What is deliberately absent: anything needing rendered geometry (reflow, target
size), anything needing judgement (is this alt text *good*), and colour
contrast — which is checked, but in ``theme.py``, against the palette, because
that is where it is decided rather than where it is used.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from surfaces.console.html import Document, Element, text_of

#: Elements whose accessible name can only come from their own content or ARIA.
#: Form controls are deliberately absent: they are named by a ``<label for>``
#: that lives elsewhere in the tree, so ``_form_violations`` checks those with
#: the labels in hand. Checking them here as well would report every correctly
#: labelled field as unnamed.
_INTERACTIVE_TAGS: Final[frozenset[str]] = frozenset({"a", "button"})

#: The form controls a ``<label for>`` names.
_FORM_TAGS: Final[frozenset[str]] = frozenset({"input", "select", "textarea"})

#: Input types that are not interactive controls a user names.
_UNNAMED_INPUT_TYPES: Final[frozenset[str]] = frozenset({"hidden", "submit", "reset", "button"})

#: The landmark every page needs exactly one of.
_MAIN_TAG: Final = "main"

_HEADING_TAGS: Final[tuple[str, ...]] = ("h1", "h2", "h3", "h4", "h5", "h6")


@dataclass(frozen=True, slots=True)
class Violation:
    """One accessibility failure, and the criterion that says it is one."""

    criterion: str
    rule: str
    detail: str

    def __str__(self) -> str:
        """Return the failure as one line, criterion first."""
        return f"WCAG {self.criterion} ({self.rule}): {self.detail}"


@dataclass(frozen=True, slots=True)
class Report:
    """What an audit found, and whether that is nothing."""

    violations: tuple[Violation, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether the page has no automatically detectable failure."""
        return not self.violations

    def describe(self) -> str:
        """Return every failure, one per line, for an assertion message."""
        return "\n".join(str(violation) for violation in self.violations)


def audit(document: Document) -> Report:
    """Return every automatically detectable WCAG 2.1 AA failure in ``document``."""
    return Report(violations=tuple(_document_violations(document)))


def audit_fragment(root: Element) -> Report:
    """Return the failures detectable in a page fragment, ignoring page-level rules.

    For a component test: a card or a table is not a document and has no
    ``<html lang>`` or ``<main>`` of its own, so asserting on those would fail
    for the wrong reason.
    """
    return Report(violations=tuple(_element_violations(root)))


def _document_violations(document: Document) -> Iterator[Violation]:
    """Yield the failures that are properties of a whole page."""
    if not document.lang.strip():
        yield Violation(
            criterion="3.1.1",
            rule="html-has-lang",
            detail="the page declares no language, so a screen reader guesses the pronunciation",
        )
    if not document.title.strip():
        yield Violation(
            criterion="2.4.2",
            rule="document-title",
            detail="the page has no title, which is what a user with twenty tabs open reads",
        )

    landmarks = document.body.find(_MAIN_TAG)
    if len(landmarks) != 1:
        yield Violation(
            criterion="1.3.1",
            rule="landmark-one-main",
            detail=f"a page needs exactly one <main>; this one has {len(landmarks)}",
        )

    yield from _element_violations(document.body)


def _element_violations(root: Element) -> Iterator[Violation]:
    """Yield the failures that are properties of the elements themselves."""
    yield from _naming_violations(root)
    yield from _image_violations(root)
    yield from _heading_violations(root)
    yield from _form_violations(root)
    yield from _table_violations(root)
    yield from _focus_violations(root)


def _naming_violations(root: Element) -> Iterator[Violation]:
    """Yield controls a screen reader would announce as nothing at all."""
    for node in root.walk():
        if node.tag not in _INTERACTIVE_TAGS:
            continue
        if _accessible_name(node):
            continue
        yield Violation(
            criterion="4.1.2",
            rule="control-has-name",
            detail=(
                f"a <{node.tag}> has no text, aria-label, or aria-labelledby, so it is "
                f"announced as an unnamed control"
            ),
        )


def _image_violations(root: Element) -> Iterator[Violation]:
    """Yield images with no textual alternative.

    An empty ``alt`` is correct and is not a failure: it is how a decorative
    image says "skip me", and forcing text onto one makes the page noisier.
    """
    for node in root.find("img"):
        if "alt" not in node.attributes:
            yield Violation(
                criterion="1.1.1",
                rule="image-alt",
                detail=(
                    'an <img> has no alt attribute; use alt="" if it is decorative, '
                    "which is a decision rather than an omission"
                ),
            )


def _heading_violations(root: Element) -> Iterator[Violation]:
    """Yield headings that skip a level, and headings with nothing in them.

    A skipped level is how an outline stops being an outline: a reader
    navigating by heading cannot tell whether an ``h4`` under an ``h2`` is a
    subsection or a sibling somebody styled smaller.
    """
    previous = 0
    for node in root.walk():
        if node.tag not in _HEADING_TAGS:
            continue
        level = int(node.tag[1])
        if not text_of(node).strip():
            yield Violation(
                criterion="1.3.1",
                rule="empty-heading",
                detail=f"an <{node.tag}> is empty, which puts a blank entry in the outline",
            )
        if previous and level > previous + 1:
            yield Violation(
                criterion="1.3.1",
                rule="heading-order",
                detail=f"<{node.tag}> follows <h{previous}>, skipping a level",
            )
        previous = level


def _form_violations(root: Element) -> Iterator[Violation]:
    """Yield form controls with no label associated with them."""
    labelled = {
        str(label.attribute("for"))
        for label in root.find("label")
        if label.has("for") and text_of(label).strip()
    }
    for node in root.walk():
        if node.tag not in _FORM_TAGS:
            continue
        if node.tag == "input" and str(node.attribute("type") or "text") in _UNNAMED_INPUT_TYPES:
            continue
        identifier = node.attribute("id")
        if identifier is not None and str(identifier) in labelled:
            continue
        if _accessible_name(node):
            continue
        yield Violation(
            criterion="3.3.2",
            rule="form-field-has-label",
            detail=(
                f"a <{node.tag}> named {node.attribute('name') or '(unnamed)'!r} has no "
                f"<label for>, aria-label, or aria-labelledby"
            ),
        )


def _table_violations(root: Element) -> Iterator[Violation]:
    """Yield data tables with no header row, and headers with no scope."""
    for table in root.find("table"):
        headers = table.find("th")
        if not headers:
            yield Violation(
                criterion="1.3.1",
                rule="table-has-headers",
                detail=(
                    "a <table> has no <th>, so every cell is announced without the column "
                    "it belongs to"
                ),
            )
            continue
        for header in headers:
            if not header.has("scope"):
                yield Violation(
                    criterion="1.3.1",
                    rule="th-has-scope",
                    detail=(
                        f"a <th> reading {text_of(header).strip()!r} declares no scope, so the "
                        f"association with its cells is left to the reader to guess"
                    ),
                )


def _focus_violations(root: Element) -> Iterator[Violation]:
    """Yield anything that reorders the keyboard path away from the reading order."""
    for node in root.walk():
        raw = node.attribute("tabindex")
        if raw is None or raw is True:
            continue
        try:
            order = int(str(raw))
        except ValueError:
            continue
        if order > 0:
            yield Violation(
                criterion="2.4.3",
                rule="tabindex-positive",
                detail=(
                    f"<{node.tag}> sets tabindex={order}, which moves it out of the reading "
                    f"order and ahead of everything that did not"
                ),
            )


def _accessible_name(node: Element) -> str:
    """Return what a screen reader would announce ``node`` as, or the empty string.

    The three sources this can see, in the order the accessible-name computation
    consults them. ``aria-labelledby`` is taken as naming *something* rather than
    resolved, because a reference into a page the console assembled is a
    reference the console can be trusted about — and resolving it here would
    mean this module needed the whole document to check one node.
    """
    for attribute in ("aria-label", "aria-labelledby", "title", "alt"):
        value = node.attribute(attribute)
        if value is not None and str(value).strip():
            return str(value).strip()
    if node.attribute("value") is not None and str(node.attribute("value")).strip():
        return str(node.attribute("value")).strip()
    return text_of(node).strip()


__all__ = ["Report", "Violation", "audit", "audit_fragment"]

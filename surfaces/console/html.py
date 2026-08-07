"""A page as a tree, and the one place in the console that produces markup.

Two things follow from building pages this way rather than from strings.

**Escaping happens once, here.** A console renders investigation transcripts —
attacker-influenced text by definition, since an alert payload is written by
whatever was misbehaving. Text arrives as a leaf of the tree and is escaped by
the renderer; there is no code path where a caller could concatenate its way
past that, because callers never hold markup at all.

**The page can be inspected before it is a string.** The accessibility checks in
``accessibility.py`` and the role matrix both walk this tree. Both are
assertions about structure — "every control has an accessible name", "no write
control is present for a viewer" — and structure is exactly what a rendered
string has thrown away.

The one text node that is *not* escaped is a stylesheet, which is a distinct
type rather than a flag. Escaping one would turn every ``>`` combinator into
``&gt;`` and serve the page unstyled; it is safe because ``theme.py`` builds it
from named tokens and no caller's input can reach it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from html import escape
from typing import Final, Union

#: Elements HTML defines as having no content. Rendering a closing tag for one
#: is a parse error in some browsers and silently reparented content in others.
VOID_TAGS: Final[frozenset[str]] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)

#: A fragment's tag. Deliberately unspellable as a real tag, so nobody can
#: construct one by accident and be surprised that it left no element behind.
FRAGMENT_TAG: Final = ""

_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")
_ATTRIBUTE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z][a-zA-Z0-9:-]*$")


class RawText(str):
    """Text that must reach the page unescaped, and the only kind that does.

    A type rather than a flag: a flag has to be passed correctly at every call
    site, and the one call site that forgets is the injection. Constructing one
    of these is a deliberate act, and the two places that do are the stylesheet
    and nothing else.
    """

    __slots__ = ()


#: What a child of an element may be. ``None`` is allowed and dropped, so a
#: conditional child is an expression rather than a branch at every call site.
Child = Union["Element", str, None]


@dataclass(frozen=True, slots=True)
class Element:
    """One node of a page: a tag, its attributes, and what is inside it."""

    tag: str
    attributes: Mapping[str, str | bool] = field(default_factory=dict)
    children: tuple[Element | str, ...] = ()

    def __post_init__(self) -> None:
        if self.tag != FRAGMENT_TAG and not _TAG_PATTERN.match(self.tag):
            raise ValueError(
                f"{self.tag!r} is not a tag name. A tag comes from this module's own "
                f"callers, never from data, so this is a defect rather than bad input."
            )
        for name in self.attributes:
            if not _ATTRIBUTE_PATTERN.match(name):
                raise ValueError(
                    f"{name!r} is not an attribute name. A name containing a space or a "
                    f"quote would end the tag, which is the whole shape of an injection."
                )

    @property
    def is_fragment(self) -> bool:
        """Return whether this node renders its children without a tag of its own."""
        return self.tag == FRAGMENT_TAG

    def render(self) -> str:
        """Return this subtree as HTML, every text node and attribute escaped."""
        inner = "".join(_render_child(child) for child in self.children)
        if self.is_fragment:
            return inner
        attributes = _render_attributes(self.attributes)
        if self.tag in VOID_TAGS:
            return f"<{self.tag}{attributes}/>"
        return f"<{self.tag}{attributes}>{inner}</{self.tag}>"

    def walk(self) -> Iterator[Element]:
        """Yield this element and every element beneath it, in document order.

        A fragment yields its children but not itself: it is a way of writing a
        list, not a node anybody meant to put on the page.
        """
        if not self.is_fragment:
            yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def find(self, tag: str) -> tuple[Element, ...]:
        """Return every element with ``tag`` in this subtree, in document order."""
        return tuple(found for found in self.walk() if found.tag == tag)

    def attribute(self, name: str) -> str | bool | None:
        """Return the value of ``name``, or ``None`` if this element has no such attribute."""
        return self.attributes.get(name)

    def has(self, name: str) -> bool:
        """Return whether ``name`` is present and is not a false boolean."""
        value = self.attributes.get(name)
        return value is not None and value is not False


def element(tag: str, *children: Child, **attributes: str | bool | None) -> Element:
    """Return an element, with the two naming conventions Python forces on us.

    A trailing underscore names an attribute Python reserves (``class_`` →
    ``class``, ``for_`` → ``for``). An underscore inside a name becomes the
    hyphen HTML uses (``aria_label`` → ``aria-label``), which is what makes ARIA
    and ``data-`` attributes writable as keyword arguments at all.

    A ``None`` or ``False`` attribute is omitted, so a conditional attribute
    needs no branch; ``True`` renders the bare name, which is what ``required``
    and ``disabled`` are.
    """
    return Element(
        tag=tag,
        attributes={
            _attribute_name(name): value
            for name, value in attributes.items()
            if value is not None and value is not False
        },
        children=tuple(child for child in children if child is not None),
    )


def fragment(*children: Child) -> Element:
    """Return a node that renders its children and contributes no tag of its own."""
    return Element(
        tag=FRAGMENT_TAG, children=tuple(child for child in children if child is not None)
    )


def each(children: Sequence[Child]) -> Element:
    """Return a fragment over a sequence, for the common comprehension case."""
    return fragment(*children)


def text_of(node: Element | str) -> str:
    """Return everything a reader would read in ``node``, whitespace preserved.

    What the accessibility checks use to ask whether a control has a discernible
    name, and what a test uses to ask what a cell says without caring how it was
    marked up.
    """
    if isinstance(node, str):
        return node
    return "".join(text_of(child) for child in node.children)


@dataclass(frozen=True, slots=True)
class Document:
    """A whole page: what it is called, what language it is in, and its body.

    ``lang`` has no way to be omitted. A page without one makes a screen reader
    guess the pronunciation of everything on it, and the guess is wrong for
    every locale that is not the reader's default.
    """

    title: str
    body: Element
    lang: str = "en"
    #: Rendered into ``<head>`` as one inline stylesheet. Inline because the
    #: console serves itself, and a second request for a stylesheet is a second
    #: chance for a page to arrive unstyled during an incident.
    stylesheet: str = ""

    def render(self) -> str:
        """Return the complete document, ready to serve."""
        head: list[Child] = [
            element("meta", charset="utf-8"),
            element("meta", name="viewport", content="width=device-width, initial-scale=1"),
            element("title", self.title),
        ]
        if self.stylesheet:
            head.append(element("style", RawText(self.stylesheet)))
        return (
            "<!doctype html>"
            + element(
                "html",
                element("head", *head),
                element("body", self.body),
                lang=self.lang,
            ).render()
        )


def _render_child(child: Element | str) -> str:
    """Return one child as HTML: elements recurse, text escapes, raw text does not."""
    if isinstance(child, Element):
        return child.render()
    if isinstance(child, RawText):
        return str(child)
    return escape(child, quote=False)


def _render_attributes(attributes: Mapping[str, str | bool]) -> str:
    """Return the attribute list, leading space included, every value escaped."""
    rendered = [
        name if value is True else f'{name}="{escape(str(value), quote=True)}"'
        for name, value in attributes.items()
    ]
    return (" " + " ".join(rendered)) if rendered else ""


def _attribute_name(name: str) -> str:
    """Return the HTML spelling of a Python keyword argument name."""
    return name.rstrip("_").replace("_", "-")


__all__ = [
    "FRAGMENT_TAG",
    "VOID_TAGS",
    "Child",
    "Document",
    "Element",
    "RawText",
    "each",
    "element",
    "fragment",
    "text_of",
]

"""The element tree everything else in the console renders through.

A console is the one surface where a string built by concatenation becomes a
cross-site scripting hole, so nothing here concatenates: a page is a tree, text
is a leaf, and the only code that produces markup is the renderer at the bottom
of this module. That is also what makes the accessibility checks possible —
they walk the tree, which is a thing that can be inspected, rather than the
string, which is not.
"""

from __future__ import annotations

import pytest

from surfaces.console.html import Document, Element, element, fragment, text_of


def test_a_text_child_is_escaped_rather_than_trusted() -> None:
    rendered = element("p", "<script>alert(1)</script>").render()

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_an_attribute_value_is_escaped_including_the_quote_that_would_end_it() -> None:
    rendered = element("a", "run", href='"><script>x</script>').render()

    assert "<script>" not in rendered
    assert "&quot;&gt;" in rendered


def test_a_trailing_underscore_names_an_attribute_python_reserves() -> None:
    rendered = element("label", "Team", for_="team-input", class_="field").render()

    assert 'for="team-input"' in rendered
    assert 'class="field"' in rendered


def test_an_underscore_inside_a_name_becomes_the_hyphen_html_uses() -> None:
    rendered = element("button", "Approve", aria_label="Approve the restart").render()

    assert 'aria-label="Approve the restart"' in rendered


def test_a_void_element_is_self_closing_and_never_gets_a_closing_tag() -> None:
    rendered = element("input", type="text", name="q").render()

    assert rendered.startswith("<input ")
    assert rendered.endswith("/>")
    assert "</input>" not in rendered


def test_a_boolean_attribute_is_present_when_true_and_absent_when_false() -> None:
    assert "required" in element("input", required=True).render()
    assert "required" not in element("input", required=False).render()


def test_none_children_are_dropped_so_a_conditional_child_needs_no_branch() -> None:
    rendered = element("div", "kept", None, element("span", "also kept")).render()

    assert rendered == "<div>kept<span>also kept</span></div>"


def test_a_fragment_renders_its_children_without_a_wrapper_of_its_own() -> None:
    rendered = element("div", fragment(element("span", "a"), element("span", "b"))).render()

    assert rendered == "<div><span>a</span><span>b</span></div>"


def test_walking_a_tree_reaches_every_element_including_nested_ones() -> None:
    tree = element("main", element("section", element("h2", "Runs"), element("p", "none yet")))

    assert [found.tag for found in tree.walk()] == ["main", "section", "h2", "p"]


def test_find_returns_every_element_of_a_tag_in_document_order() -> None:
    tree = element("ul", element("li", "one"), element("li", "two"))

    assert [text_of(found) for found in tree.find("li")] == ["one", "two"]


def test_the_text_of_a_subtree_is_everything_a_reader_would_read() -> None:
    tree = element("p", "restart ", element("strong", "checkout"), " now")

    assert text_of(tree) == "restart checkout now"


def test_a_document_carries_a_language_and_a_title_because_both_are_required() -> None:
    rendered = Document(title="Runs", body=element("main", "hello")).render()

    assert rendered.startswith("<!doctype html>")
    assert '<html lang="en">' in rendered
    assert "<title>Runs</title>" in rendered


def test_a_document_title_is_escaped_like_any_other_text() -> None:
    rendered = Document(title="<script>", body=element("main")).render()

    assert "<script>" not in rendered


def test_an_element_refuses_a_tag_that_is_not_a_tag() -> None:
    with pytest.raises(ValueError, match="tag"):
        Element(tag="not a tag")


def test_an_attribute_name_that_could_break_out_of_the_tag_is_refused() -> None:
    with pytest.raises(ValueError, match="attribute"):
        element("div", **{"onclick=x y": "1"})

"""The accessibility harness, checked against pages that are deliberately wrong.

A checker nobody has shown a failure to is a checker that returns "no problems"
for every input, and that is indistinguishable from a working one until it
matters. So each rule gets a page that breaks it and a page that does not.
"""

from __future__ import annotations

from surfaces.console.accessibility import audit, audit_fragment
from surfaces.console.html import Document, element


def _page(*body: object) -> Document:
    """Return a minimal well-formed page wrapping ``body``."""
    return Document(title="Runs", body=element("div", element("main", *body)))  # type: ignore[arg-type]


def _rules(document: Document) -> set[str]:
    """Return the rule names an audit of ``document`` reported."""
    return {violation.rule for violation in audit(document).violations}


def test_a_well_formed_page_reports_nothing() -> None:
    document = _page(
        element("h1", "Runs"),
        element("h2", "Filters"),
        element("label", "Team", for_="team"),
        element("input", id="team", name="team", type="text"),
        element("button", "Apply"),
        element(
            "table",
            element("thead", element("tr", element("th", "Run", scope="col"))),
            element("tbody", element("tr", element("td", "run-1"))),
        ),
        element("img", src="/spark.svg", alt=""),
    )

    report = audit(document)

    assert report.passed, report.describe()


def test_a_page_with_no_language_is_reported() -> None:
    document = Document(title="Runs", body=element("main", "hi"), lang="")

    assert "html-has-lang" in _rules(document)


def test_a_page_with_no_title_is_reported() -> None:
    document = Document(title="  ", body=element("main", "hi"))

    assert "document-title" in _rules(document)


def test_a_page_with_no_main_landmark_is_reported() -> None:
    document = Document(title="Runs", body=element("div", "hi"))

    assert "landmark-one-main" in _rules(document)


def test_a_page_with_two_main_landmarks_is_reported() -> None:
    document = Document(title="Runs", body=element("div", element("main"), element("main")))

    assert "landmark-one-main" in _rules(document)


def test_a_button_a_reader_would_announce_as_nothing_is_reported() -> None:
    assert "control-has-name" in _rules(_page(element("button")))


def test_a_button_named_only_by_aria_label_is_accepted() -> None:
    document = _page(element("button", aria_label="Approve the restart"))

    assert "control-has-name" not in _rules(document)


def test_an_image_with_no_alt_attribute_is_reported() -> None:
    assert "image-alt" in _rules(_page(element("img", src="/x.png")))


def test_a_decorative_image_declaring_an_empty_alt_is_accepted() -> None:
    assert "image-alt" not in _rules(_page(element("img", src="/x.png", alt="")))


def test_a_heading_that_skips_a_level_is_reported() -> None:
    document = _page(element("h1", "Runs"), element("h3", "Filters"))

    assert "heading-order" in _rules(document)


def test_a_heading_that_returns_to_a_shallower_level_is_not_a_skip() -> None:
    document = _page(element("h1", "Runs"), element("h2", "One"), element("h2", "Two"))

    assert "heading-order" not in _rules(document)


def test_an_empty_heading_is_reported() -> None:
    assert "empty-heading" in _rules(_page(element("h1", "Runs"), element("h2", " ")))


def test_an_input_with_no_label_of_any_kind_is_reported() -> None:
    assert "form-field-has-label" in _rules(_page(element("input", name="q", type="text")))


def test_an_input_labelled_by_a_for_attribute_is_accepted() -> None:
    document = _page(
        element("label", "Search", for_="q"), element("input", id="q", name="q", type="text")
    )

    assert "form-field-has-label" not in _rules(document)


def test_a_label_with_no_text_does_not_count_as_a_label() -> None:
    document = _page(element("label", "", for_="q"), element("input", id="q", name="q"))

    assert "form-field-has-label" in _rules(document)


def test_a_hidden_input_needs_no_label_because_nobody_fills_it_in() -> None:
    document = _page(element("input", type="hidden", name="cursor", value="42"))

    assert "form-field-has-label" not in _rules(document)


def test_a_table_with_no_header_row_is_reported() -> None:
    document = _page(element("table", element("tr", element("td", "run-1"))))

    assert "table-has-headers" in _rules(document)


def test_a_header_cell_with_no_scope_is_reported() -> None:
    document = _page(element("table", element("tr", element("th", "Run"))))

    assert "th-has-scope" in _rules(document)


def test_a_positive_tabindex_is_reported_because_it_reorders_the_keyboard_path() -> None:
    assert "tabindex-positive" in _rules(_page(element("button", "Go", tabindex="3")))


def test_a_tabindex_of_minus_one_is_accepted_because_it_removes_rather_than_reorders() -> None:
    assert "tabindex-positive" not in _rules(_page(element("button", "Go", tabindex="-1")))


def test_a_fragment_is_not_judged_by_the_page_level_rules_it_cannot_satisfy() -> None:
    card = element("article", element("h2", "Approval"), element("button", "Approve"))

    assert audit_fragment(card).passed


def test_a_fragment_is_still_judged_by_the_rules_it_can_break() -> None:
    card = element("article", element("button"))

    assert "control-has-name" in {v.rule for v in audit_fragment(card).violations}


def test_a_violation_reads_as_one_line_naming_the_criterion() -> None:
    report = audit(_page(element("button")))

    assert str(report.violations[0]).startswith("WCAG 4.1.2 (control-has-name):")

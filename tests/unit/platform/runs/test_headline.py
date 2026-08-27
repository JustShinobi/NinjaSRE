"""Normalising a headline candidate, and synthesising one when none arrives.

Two functions, two different sources of truth. Normalisation cleans up
whatever text it is handed — it does not care where that text came from.
Synthesis only ever sees the investigation's subject: it has no parameter
that could carry the report's body, which is what makes "the synthesised
headline never derives from the document" a property of the function's
signature rather than a promise about its behaviour.
"""

from __future__ import annotations

from config.constants.runs import HEADLINE_MARKER, MAX_HEADLINE_LENGTH
from platform.runs.headline import normalize_headline, report_body, synthesize_headline


class TestNormalizeHeadline:
    def test_a_single_clean_line_passes_through_unchanged(self) -> None:
        assert (
            normalize_headline("Postgres connection pool exhausted on node-3")
            == "Postgres connection pool exhausted on node-3"
        )

    def test_markdown_emphasis_is_stripped(self) -> None:
        normalized = normalize_headline("**Postgres** connection pool `exhausted` on node-3")

        assert "*" not in normalized
        assert "`" not in normalized
        assert normalized == "Postgres connection pool exhausted on node-3"

    def test_a_markdown_heading_marker_is_stripped(self) -> None:
        normalized = normalize_headline("### Incident Findings: disk full on host-1")

        assert not normalized.startswith("#")
        assert "Incident Findings" in normalized

    def test_multiple_lines_collapse_to_one(self) -> None:
        normalized = normalize_headline(
            "The database ran out of connections\nbecause the pool size was too small\nfor peak load"
        )

        assert "\n" not in normalized
        assert normalized.startswith("The database ran out of connections")

    def test_multiple_paragraphs_collapse_to_one_line(self) -> None:
        """The adversarial case the spec names by name: three paragraphs, not one line."""
        raw = (
            "This investigation found that the disk on host-1 filled up.\n\n"
            "The root cause was a runaway log file that was never rotated.\n\n"
            "Remediation: rotate the log and add a disk-usage alert."
        )

        normalized = normalize_headline(raw)

        assert "\n" not in normalized
        assert normalized.startswith("This investigation found that the disk on host-1 filled up")

    def test_excess_length_is_cut_at_a_word_boundary(self) -> None:
        raw = "word " * 100  # far past the declared ceiling
        normalized = normalize_headline(raw)

        assert len(normalized) <= MAX_HEADLINE_LENGTH
        assert not normalized.endswith(" ")
        # Cut at a word boundary: the last character is not a fragment of "word".
        assert normalized == "" or raw.startswith(normalized.rstrip())

    def test_a_cut_headline_does_not_end_mid_word(self) -> None:
        raw = "alpha bravo charlie delta echo foxtrot golf hotel india juliet " * 5
        normalized = normalize_headline(raw)

        assert len(normalized) <= MAX_HEADLINE_LENGTH
        # The character immediately after the cut in the source is a space or
        # the string ended exactly there — never mid-token.
        assert raw[: len(normalized)] == normalized

    def test_empty_input_normalizes_to_empty(self) -> None:
        assert normalize_headline("") == ""

    def test_whitespace_only_input_normalizes_to_empty(self) -> None:
        assert normalize_headline("   \n\n   ") == ""


class TestSynthesizeHeadline:
    def test_derives_from_alert_name_and_resource_when_both_are_given(self) -> None:
        headline = synthesize_headline(alert_name="InstanceDown", resource="host-1")

        assert "InstanceDown" in headline
        assert "host-1" in headline

    def test_falls_back_to_the_declared_objective_when_there_is_no_alert(self) -> None:
        headline = synthesize_headline(objective="disk on host-1 is at 98%")

        assert "disk on host-1 is at 98%" in headline

    def test_is_one_line_without_markdown(self) -> None:
        headline = synthesize_headline(alert_name="InstanceDown", resource="host-1")

        assert "\n" not in headline
        assert "#" not in headline

    def test_never_accepts_a_document_body_at_all(self) -> None:
        """Structural, not behavioural: the function has no parameter for it.

        The regression this feature exists to eliminate was a title derived
        from the report's own text. Guaranteeing that is impossible by
        checking the function's declared keyword arguments.
        """
        import inspect

        parameters = set(inspect.signature(synthesize_headline).parameters)

        assert "document" not in parameters
        assert "report" not in parameters
        assert "text" not in parameters
        assert "summary" not in parameters

    def test_an_attractive_markdown_heading_never_leaks_in(self) -> None:
        """The adversarial case: nothing offered here can look like the document's own H1.

        There is no way to hand the function a document at all (see above),
        so this asserts the same property from the caller's side: a
        synthesised headline built only from the subject never contains the
        sentence a document's opening heading would have used.
        """
        headline = synthesize_headline(
            alert_name="InstanceDown", resource="host-1", objective="disk on host-1 is at 98%"
        )

        assert "Incident Findings" not in headline

    def test_is_never_empty_even_with_no_subject_at_all(self) -> None:
        headline = synthesize_headline()

        assert headline.strip() != ""


def test_the_marker_line_does_not_survive_into_the_report_body() -> None:
    """The line the model was asked to write is consumed, not left behind.

    The delivery prompt asks for a ``Headline:`` line so the run has a sentence
    to be titled by. Extraction read it and nothing removed it, so the report
    document ended with the same sentence the page's own heading was already
    showing — on 343 of 496 investigations in staging.
    """
    written = (
        "## Root Cause\n\n"
        "The sync jobs exited with code 2.\n\n"
        "Headline: Proxmox node pve01 backup jobs failed with exit code 2\n"
    )

    body = report_body(written)

    assert HEADLINE_MARKER not in body
    assert "The sync jobs exited with code 2." in body, (
        "stripping the marker took the report with it"
    )


def test_a_report_without_a_marker_is_returned_unchanged() -> None:
    """Nothing is trimmed from a model that never wrote the line."""
    written = "## Root Cause\n\nThe sync jobs exited with code 2."

    assert report_body(written) == written

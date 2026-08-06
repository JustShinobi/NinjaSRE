"""What a reviewer sees, and a 10,000-line diff that stays reviewable.

The requirement is not "large diffs are handled". It is that a large diff is
*summarised* and never truncated without saying so — because a truncated diff
looks exactly like a small one, and the reviewer who approves it has no way to
know there were nine thousand more lines behind it.

So the assertions here are about what the summary *says* as much as what it
shows: that it is a summary, how much it omitted, and that every omitted line is
still reachable through drill-down. A summary that dropped lines correctly and
did not admit it would fail this file.
"""

from __future__ import annotations

import pytest

from config.constants.security import DIFF_SUMMARY_SECTION_LINES, DIFF_SUMMARY_THRESHOLD_LINES
from platform.approvals.diff.engine import DiffEngine, DiffOperation, render_value
from platform.approvals.diff.renderers import RENDERERS
from platform.approvals.diff.summarise import summarise
from platform.approvals.models import ChangeType

pytestmark = pytest.mark.unit


@pytest.fixture
def engine() -> DiffEngine:
    """Return the diff engine over the shipped renderers and guardrail ruleset."""
    return DiffEngine(renderers=RENDERERS)


# --- Type-aware rendering ----------------------------------------------------


def test_every_change_type_has_a_renderer() -> None:
    """A change type nobody can review is one that gets approved unread."""
    assert set(RENDERERS) == set(ChangeType)


def test_a_configuration_change_is_diffed_by_path(engine: DiffEngine) -> None:
    diff = engine.diff(
        ChangeType.CONFIGURATION,
        {"policies": {"masking": {"level": "standard"}}, "budgets": {"iterations": 8}},
        {"policies": {"masking": {"level": "strict"}}, "budgets": {"iterations": 8}},
    )

    assert diff.line_count == 1
    line = diff.lines()[0]
    assert line.path == "policies.masking.level"
    assert line.operation is DiffOperation.CHANGED
    assert (line.before, line.after) == ("standard", "strict")


def test_a_removed_configuration_path_is_a_change(engine: DiffEngine) -> None:
    """A gated field that could be deleted invisibly is gated in name only."""
    diff = engine.diff(ChangeType.CONFIGURATION, {"policies": {"masking": "strict"}}, {})

    assert [line.operation for line in diff.lines()] == [DiffOperation.REMOVED]


def test_configuration_lines_are_grouped_by_area(engine: DiffEngine) -> None:
    diff = engine.diff(
        ChangeType.CONFIGURATION,
        {"policies": {"masking": "standard"}, "budgets": {"iterations": 8}},
        {"policies": {"masking": "strict"}, "budgets": {"iterations": 12}},
    )

    assert [section.title for section in diff.sections] == ["budgets", "policies"]


def test_a_prompt_change_is_diffed_by_line(engine: DiffEngine) -> None:
    diff = engine.diff(
        ChangeType.PROMPT,
        {"investigation": "one\ntwo\nthree"},
        {"investigation": "one\ntwo and a half\nthree"},
    )

    operations = [line.operation for line in diff.lines()]
    assert DiffOperation.REMOVED in operations
    assert DiffOperation.ADDED in operations
    assert "two and a half" in "\n".join(diff.render())


def test_an_unchanged_prompt_produces_no_diff(engine: DiffEngine) -> None:
    diff = engine.diff(ChangeType.PROMPT, {"investigation": "same"}, {"investigation": "same"})

    assert diff.is_empty


def test_a_capability_change_is_diffed_as_a_set(engine: DiffEngine) -> None:
    diff = engine.diff(
        ChangeType.CAPABILITY,
        {"enabled": ["datadog_search_logs"]},
        {"enabled": ["datadog_search_logs", "kubernetes_restart_deployment"]},
    )

    assert [section.title for section in diff.sections] == ["enabling"]
    assert [line.path for line in diff.lines()] == ["kubernetes_restart_deployment"]


def test_enabling_is_reported_before_disabling(engine: DiffEngine) -> None:
    """The half that widens what the agent may do comes first."""
    diff = engine.diff(ChangeType.CAPABILITY, {"enabled": ["a"]}, {"enabled": ["b"]})

    assert [section.title for section in diff.sections] == ["enabling", "disabling"]


def test_a_knowledge_proposal_renders_its_document(engine: DiffEngine) -> None:
    diff = engine.diff(
        ChangeType.KNOWLEDGE,
        {},
        {"title": "Checkout OOMs under load", "body": "Raise the memory limit."},
    )

    paths = [line.path for line in diff.lines()]
    assert paths == ["title", "body"]
    assert all(line.operation is DiffOperation.ADDED for line in diff.lines())


def test_a_remediation_renders_its_steps_and_its_rollback(engine: DiffEngine) -> None:
    """Feature 017's contract: the undo is shown beside the action, not behind a link."""
    diff = engine.diff(
        ChangeType.REMEDIATION,
        {},
        {
            "steps": [{"capability": "k8s_restart", "description": "Restart checkout"}],
            "rollback": [{"capability": "k8s_scale", "description": "Scale back to 3"}],
        },
    )

    assert [section.title for section in diff.sections] == ["would run", "would be undone by"]


def test_a_remediation_step_carries_its_arguments(engine: DiffEngine) -> None:
    """An approval against a description that omitted the target is not one."""
    diff = engine.diff(
        ChangeType.REMEDIATION,
        {},
        {
            "steps": [
                {
                    "capability": "k8s_restart",
                    "description": "Restart",
                    "arguments": {"deployment": "checkout"},
                }
            ]
        },
    )

    assert "checkout" in "\n".join(diff.render())


# --- Guardrail filtering (T038) ----------------------------------------------


def test_a_secret_in_a_proposed_value_is_redacted_before_display(
    engine: DiffEngine,
) -> None:
    """Article IV: the diff is shown to a human and then kept forever."""
    secret = "AKIAIOSFODNN7EXAMPLE"
    diff = engine.diff(
        ChangeType.CONFIGURATION, {}, {"integrations": {"aws": {"access_key": secret}}}
    )

    assert secret not in "\n".join(diff.render())
    assert secret not in repr(diff.to_record())


# --- Long values -------------------------------------------------------------


def test_a_very_long_value_is_described_rather_than_printed() -> None:
    rendered = render_value("x" * 50_000)

    assert rendered.startswith("<50000 characters, fingerprint ")
    assert len(rendered) < 100


def test_a_short_value_is_printed_whole() -> None:
    assert render_value("strict") == "strict"


def test_absent_is_distinguishable_from_a_none_value() -> None:
    """A configuration value of ``None`` is not the same as no value at all."""
    assert render_value(None) != render_value("None")


# --- Ten thousand lines ------------------------------------------------------


@pytest.fixture
def huge_diff(engine: DiffEngine) -> object:
    """Return a diff of ten thousand changed configuration paths."""
    current = {"area": {f"field_{index}": index for index in range(10_000)}}
    proposed = {"area": {f"field_{index}": index + 1 for index in range(10_000)}}
    return engine.diff(ChangeType.CONFIGURATION, current, proposed)


def test_a_ten_thousand_line_diff_is_produced_in_full(huge_diff: object) -> None:
    """The whole thing exists. Only the *presentation* is reduced."""
    assert huge_diff.line_count == 10_000  # type: ignore[attr-defined]


def test_a_ten_thousand_line_diff_is_summarised_not_truncated(huge_diff: object) -> None:
    summary = summarise(huge_diff)  # type: ignore[arg-type]

    assert summary.is_summarised
    assert summary.total_lines == 10_000
    assert summary.shown_lines <= DIFF_SUMMARY_SECTION_LINES * len(summary.sections)
    assert summary.omitted_lines == 10_000 - summary.shown_lines


def test_the_summary_says_it_is_one(huge_diff: object) -> None:
    """A summary a surface can render without mentioning that it is a summary
    is a summary somebody will render that way."""
    rendered = summarise(huge_diff).render()  # type: ignore[arg-type]

    assert "Showing" in rendered[0]
    assert "10000" in rendered[0]
    assert any("further change" in line for line in rendered)


def test_every_section_survives_the_summary(huge_diff: object) -> None:
    """Dropping a whole section would hide that an area was touched at all."""
    summary = summarise(huge_diff)  # type: ignore[arg-type]

    assert {section.title for section in summary.sections} == {
        section.title
        for section in huge_diff.sections  # type: ignore[attr-defined]
    }


def test_drill_down_returns_an_omitted_section_whole(huge_diff: object) -> None:
    summary = summarise(huge_diff)  # type: ignore[arg-type]

    expanded = summary.drill_down("area")

    assert len(expanded) == 10_000


def test_drilling_into_a_section_that_is_not_there_names_what_is(
    huge_diff: object,
) -> None:
    summary = summarise(huge_diff)  # type: ignore[arg-type]

    with pytest.raises(KeyError, match="area"):
        summary.drill_down("nothing-like-this")


def test_a_small_diff_is_not_marked_as_summarised(engine: DiffEngine) -> None:
    diff = engine.diff(ChangeType.CONFIGURATION, {"a": 1}, {"a": 2})

    summary = summarise(diff)

    assert not summary.is_summarised
    assert summary.omitted_lines == 0
    assert summary.shown_lines == summary.total_lines


def test_the_threshold_is_where_summarising_starts(engine: DiffEngine) -> None:
    """Exactly at the threshold is still shown whole; one past it is not."""
    at_limit = {f"f{index}": index for index in range(DIFF_SUMMARY_THRESHOLD_LINES)}
    over = {f"f{index}": index for index in range(DIFF_SUMMARY_THRESHOLD_LINES + 1)}

    assert not summarise(engine.diff(ChangeType.CONFIGURATION, {}, at_limit)).is_summarised
    assert summarise(engine.diff(ChangeType.CONFIGURATION, {}, over)).is_summarised


def test_the_record_keeps_the_whole_diff_behind_the_summary(huge_diff: object) -> None:
    """Reconstructing a decision needs what the reviewer saw *and* what they decided about."""
    record = summarise(huge_diff).to_record()  # type: ignore[arg-type]

    assert record["is_summarised"] is True
    assert record["diff"]["line_count"] == 10_000

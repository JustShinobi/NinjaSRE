"""A log line is structured, correlated, filtered, and tunable without a restart.

Four properties, and the third is the one with teeth. Guardrail filtering at
emission means the last thing that happens before a line leaves the process is
a scan — so a vendor's error message pasted into a log call cannot carry a token
out of the deployment, whoever wrote the call site and whatever they knew about
what was in the string.

The fourth exists because of what an operator actually does at 03:00: turn one
subsystem's logging up. Doing that by restarting the deployment means restarting
the thing that is misbehaving, which loses the state they were trying to look at.
"""

from __future__ import annotations

import logging

import pytest

from config.constants.observability import (
    LOG_CORRELATION_FIELD,
    LOG_FIELDS,
    LOG_GUARDRAIL_FIELD,
    MAX_LOG_VALUE_CHARS,
    NINJASRE_LOG_MODULE_LEVELS_ENV,
)
from platform.observability.logging import (
    bind_correlation_id,
    clear_correlation_id,
    correlated,
    current_correlation_id,
    guardrail_processor,
    module_levels,
    reload_module_levels,
    set_module_level,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    """Correlation state is process-wide; a leaked binding fails the next test."""
    clear_correlation_id()


# -- the fixed field set (FR-011) ---------------------------------------------


def test_the_field_set_is_fixed_and_names_the_four_a_query_needs() -> None:
    assert LOG_FIELDS == ("timestamp", "level", "logger", "event")


def test_a_line_carries_every_declared_field(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from platform.observability.logging import configure_logging, get_logger

    configure_logging(force=True, log_format="json")
    get_logger("platform.observability.example").info("evidence.collected", entries=17)

    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])

    assert set(LOG_FIELDS) <= set(line)
    assert line["event"] == "evidence.collected"
    assert line["logger"] == "platform.observability.example"
    assert line["entries"] == 17


# -- the correlation identifier (FR-012) --------------------------------------


def test_no_correlation_identifier_is_invented_when_there_is_none() -> None:
    assert current_correlation_id() == ""


def test_a_bound_identifier_reaches_every_line(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from platform.observability.logging import configure_logging, get_logger

    configure_logging(force=True, log_format="json")
    bind_correlation_id("inv-2026-08-07-001")
    logger = get_logger("platform.observability.example")
    logger.info("first")
    logger.info("second")

    lines = [json.loads(text) for text in capsys.readouterr().err.strip().splitlines()[-2:]]

    assert [line[LOG_CORRELATION_FIELD] for line in lines] == [
        "inv-2026-08-07-001",
        "inv-2026-08-07-001",
    ]


def test_the_binding_is_scoped_and_restores_what_it_replaced() -> None:
    bind_correlation_id("outer")

    with correlated("inner"):
        assert current_correlation_id() == "inner"

    assert current_correlation_id() == "outer"


def test_clearing_removes_it_rather_than_emptying_it() -> None:
    bind_correlation_id("inv-1")
    clear_correlation_id()

    assert current_correlation_id() == ""


# -- guardrail filtering at emission (FR-013) ---------------------------------


def test_a_secret_in_a_log_value_is_redacted_before_emission() -> None:
    event = guardrail_processor(
        None, "info", {"event": "vendor.error", "detail": "AKIAIOSFODNN7EXAMPLE refused"}
    )

    assert "AKIAIOSFODNN7EXAMPLE" not in event["detail"]
    assert event[LOG_GUARDRAIL_FIELD]


def test_a_secret_in_the_event_name_itself_is_redacted() -> None:
    event = guardrail_processor(None, "info", {"event": "failed for AKIAIOSFODNN7EXAMPLE"})

    assert "AKIAIOSFODNN7EXAMPLE" not in event["event"]


def test_a_clean_line_is_unchanged_and_carries_no_guardrail_field() -> None:
    """A field that appeared on every line would say nothing about any of them."""
    event = guardrail_processor(
        None, "info", {"event": "evidence.collected", "capability": "grafana.query"}
    )

    assert event == {"event": "evidence.collected", "capability": "grafana.query"}


def test_a_non_string_value_survives_the_scan_as_itself() -> None:
    event = guardrail_processor(
        None, "info", {"event": "e", "entries": 17, "ok": True, "ratio": 0.5}
    )

    assert (event["entries"], event["ok"], event["ratio"]) == (17, True, 0.5)


def test_a_value_nested_in_a_mapping_is_scanned_too() -> None:
    event = guardrail_processor(
        None, "info", {"event": "e", "context": {"key": "AKIAIOSFODNN7EXAMPLE"}}
    )

    assert "AKIAIOSFODNN7EXAMPLE" not in str(event["context"])


def test_a_value_in_a_sequence_is_scanned_too() -> None:
    event = guardrail_processor(None, "info", {"event": "e", "keys": ["AKIAIOSFODNN7EXAMPLE"]})

    assert "AKIAIOSFODNN7EXAMPLE" not in str(event["keys"])


def test_an_enormous_value_is_scanned_and_then_truncated() -> None:
    """A megabyte of vendor error text in one line is a log pipeline outage."""
    event = guardrail_processor(None, "info", {"event": "e", "body": "x" * 100_000})

    assert len(event["body"]) <= MAX_LOG_VALUE_CHARS + len("… truncated")


def test_the_scan_never_raises_on_a_value_it_cannot_render() -> None:
    class Awkward:
        def __str__(self) -> str:
            raise RuntimeError("this object refuses to render")

    event = guardrail_processor(None, "info", {"event": "e", "thing": Awkward()})

    assert event["event"] == "e"


# -- per-module levels, without a restart (FR-014) ----------------------------


def test_a_module_level_takes_effect_immediately() -> None:
    set_module_level("platform.memory", "DEBUG")

    assert logging.getLogger("platform.memory").isEnabledFor(logging.DEBUG)
    assert module_levels()["platform.memory"] == "DEBUG"

    set_module_level("platform.memory", "WARNING")

    assert not logging.getLogger("platform.memory").isEnabledFor(logging.DEBUG)


def test_turning_one_module_up_leaves_the_others_alone() -> None:
    set_module_level("platform.memory", "DEBUG")

    assert not logging.getLogger("platform.scheduler").isEnabledFor(logging.DEBUG)


def test_an_unknown_level_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="LOUD"):
        set_module_level("platform.memory", "LOUD")


def test_the_environment_is_re_read_on_demand() -> None:
    applied = reload_module_levels(
        {NINJASRE_LOG_MODULE_LEVELS_ENV: "platform.memory=DEBUG,core.agent=WARNING"}
    )

    assert applied == {"core.agent": "WARNING", "platform.memory": "DEBUG"}
    assert logging.getLogger("core.agent").level == logging.WARNING


def test_a_malformed_entry_is_skipped_rather_than_failing_the_reload() -> None:
    """A typo in one pair must not silence the pair beside it."""
    applied = reload_module_levels(
        {NINJASRE_LOG_MODULE_LEVELS_ENV: "nonsense,platform.memory=DEBUG,core.agent=LOUD"}
    )

    assert applied == {"platform.memory": "DEBUG"}


def test_reloading_an_empty_setting_clears_what_was_applied() -> None:
    reload_module_levels({NINJASRE_LOG_MODULE_LEVELS_ENV: "platform.memory=DEBUG"})

    assert reload_module_levels({}) == {}
    assert logging.getLogger("platform.memory").level == logging.NOTSET

"""Asking a resource for its logs, which no investigation could do.

``LogSource`` declared the port, ``LogReader`` bounded the query, the catalogue
resolved a resource to its stream selector — and no capability tool called any of
it. An investigation could read metrics and changes and never a log line.

The shape follows ``changes_in_window`` deliberately, and for the same reasons:

**It takes a resource, not a selector.** A tool that accepted a raw LogQL
selector would be a second query language the model composes, and the deployment
would have to keep it working. The catalogue owns the mapping; the model names a
resource.

**The bound travels with the answer.** Five hundred lines out of ten thousand
reads exactly like a quiet guest unless the shortfall is in the value, so the
summary is carried, never dropped.

**Unavailable, not-found, and empty are three different answers.** Only one of
them means "the logs are not where the problem is".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from capabilities.tools.logs import binding
from capabilities.tools.logs.logs_for_resource import TOOL_NAME, logs_for_resource

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


def _answer(lines: int = 2, truncated: bool = False) -> object:
    from platform.observation.bridge.logs import LogAnswer, LogQueryBound
    from platform.observation.bridge.ports import LogLine

    return LogAnswer(
        selector='{job="proxmox-syslog"} |= "pve-container@100"',
        start=datetime(2026, 8, 12, 9, 0, tzinfo=UTC),
        end=AT,
        lines=tuple(
            LogLine(observed_at=AT, line=f"line {number}", labels={"host": "pve01"})
            for number in range(lines)
        ),
        bound=LogQueryBound(window_seconds=3_600, limit=500),
        truncated=truncated,
    )


class _Access:
    def __init__(self, answer: object = None) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def logs_for(self, resource: str, *, at: datetime) -> object:
        del at
        self.asked.append(resource)
        return self.answer


@pytest.fixture(autouse=True)
def _unbound() -> object:
    previous = binding.bind(None)
    yield
    binding.restore(previous)


async def test_a_deployment_with_no_log_source_is_unavailable_not_quiet() -> None:
    """A negative nobody earned is the one answer that misleads an investigation."""
    from core.capability.result import CapabilityErrorClass

    result = await logs_for_resource("res-a")

    assert not result.succeeded
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE


async def test_a_resource_the_estate_does_not_hold_is_a_finding_of_its_own() -> None:
    from core.capability.result import CapabilityErrorClass

    binding.bind(_Access(answer=None))

    result = await logs_for_resource("res-nobody-watches")

    assert not result.succeeded
    assert result.error.classification is CapabilityErrorClass.NOT_FOUND


async def test_the_lines_come_back_with_the_bound_that_shaped_them() -> None:
    access = _Access(answer=_answer(lines=2))
    binding.bind(access)

    result = await logs_for_resource("res-a")

    assert result.succeeded
    assert access.asked == ["res-a"]
    assert len(result.value["lines"]) == 2
    # The sentence that must accompany the lines wherever they are shown.
    assert result.value["summary"]
    assert result.value["complete"] is True


async def test_a_truncated_answer_says_so_rather_than_reading_as_the_whole_story() -> None:
    binding.bind(_Access(answer=_answer(lines=2, truncated=True)))

    result = await logs_for_resource("res-a")

    assert result.truncated is True
    assert result.value["complete"] is False


async def test_a_source_that_did_not_answer_is_reported_as_unreachable() -> None:
    """Not as an empty result: one is "we could not look", the other is a finding."""
    from core.capability.result import CapabilityErrorClass
    from platform.observation.bridge.errors import LogSourceUnreachable

    class _Broken:
        async def logs_for(self, resource: str, *, at: datetime) -> object:
            raise LogSourceUnreachable("loki", reason="connection refused")

    binding.bind(_Broken())

    result = await logs_for_resource("res-a")

    assert not result.succeeded
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE
    assert "connection refused" in result.error.message


async def test_the_tool_is_discoverable_under_its_declared_name() -> None:
    """A capability discovery walks the package; a tool nothing finds is unwired."""
    from core.capability.registered import capability_marker

    assert TOOL_NAME == "logs_for_resource"
    assert capability_marker(logs_for_resource) is not None

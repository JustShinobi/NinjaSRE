"""Trello, end to end: capability, client, proxy, injection, vendor.

The seventh parity artefact. Everything else about an integration can look
finished while nothing exercises the path a real call takes — and the first
thing to notice that is the investigation which needed it.

So these drive the whole path: the registered capability, the client, the real
credential proxy with this integration's own injection rule, and a scripted
vendor on the far side. Nothing is mocked between the tool and the wire, which
is what makes a renamed response field fail here rather than at 03:00.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

#: Not a real credential. The suite asserts that none of these values reaches a
#: client, a result, or a trace, which is the property SC-003 is about.
CREDENTIAL: Final[dict[str, str]] = {
    "token": "ninjasre-scenario-key-000000",
    "board": "5f2b1c9d0000000000000000",
}


ISSUE_STATISTICS: Final = IntegrationScenario(
    key="trello-issue-statistics",
    integration="trello",
    capability="trello_issue_statistics",
    arguments={"query": "", "start": "", "end": "", "group_by": "idList"},
    responses=(
        json_response(
            [
                {"id": "c1", "idList": "l1", "name": "cart 500s"},
                {"id": "c2", "idList": "l1", "name": "checkout timeouts"},
                {"id": "c3", "idList": "l2", "name": "done thing"},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/1/boards/5f2b1c9d0000000000000000/cards",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="trello-recent-issues",
    integration="trello",
    capability="trello_recent_issues",
    arguments={"query": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            [
                {
                    "id": "c1",
                    "idList": "l1",
                    "name": "cart 500s",
                    "dateLastActivity": "2026-08-07T11:50:00Z",
                }
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from Trello",
    expected_paths=("/1/boards/5f2b1c9d0000000000000000/cards",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]

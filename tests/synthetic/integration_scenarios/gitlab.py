"""GitLab, end to end: capability, client, proxy, injection, vendor.

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
    "api_key": "ninjasre-scenario-key-000000",
}


CHANGE_STATISTICS: Final = IntegrationScenario(
    key="gitlab-change-statistics",
    integration="gitlab",
    capability="gitlab_change_statistics",
    arguments={"repository": "checkout", "start": "", "end": "", "group_by": "namespace.path"},
    responses=(
        json_response(
            [
                {"id": 1, "name": "checkout", "namespace": {"path": "acme"}},
                {"id": 2, "name": "payments", "namespace": {"path": "acme"}},
                {"id": 3, "name": "docs", "namespace": {"path": "platform"}},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 commits across",
    expected_paths=("/api/v4/projects",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="gitlab-recent-changes",
    integration="gitlab",
    capability="gitlab_recent_changes",
    arguments={"repository": "", "start": "2026-08-07T11:00:00Z", "end": "", "limit": 10},
    responses=(json_response([{"iid": 412, "title": "raise cart limit", "state": "merged"}]),),
    credential=CREDENTIAL,
    expected_summary="1 changes from GitLab",
    expected_paths=("/api/v4/merge_requests",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (CHANGE_STATISTICS, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "CHANGE_STATISTICS", "RECENT_CHANGES"]

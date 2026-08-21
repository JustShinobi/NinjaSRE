"""Google Docs, end to end: capability, client, proxy, injection, vendor.

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
    "token": "ninjasre-scenario-token-000000",
}


ISSUE_STATISTICS: Final = IntegrationScenario(
    key="google_docs-issue-statistics",
    integration="google_docs",
    capability="google_docs_issue_statistics",
    arguments={"query": "name contains 'runbook'", "start": "", "end": "", "group_by": "mimeType"},
    responses=(
        json_response(
            {
                "files": [
                    {
                        "id": "d1",
                        "name": "Checkout runbook",
                        "mimeType": "application/vnd.google-apps.document",
                    },
                    {
                        "id": "d2",
                        "name": "Cart limits",
                        "mimeType": "application/vnd.google-apps.document",
                    },
                    {
                        "id": "s1",
                        "name": "Capacity",
                        "mimeType": "application/vnd.google-apps.spreadsheet",
                    },
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/drive/v3/files",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="google_docs-recent-issues",
    integration="google_docs",
    capability="google_docs_recent_issues",
    arguments={"query": "name contains 'runbook'", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "files": [
                    {"id": "d1", "name": "Checkout runbook", "modifiedTime": "2026-02-01T09:00:00Z"}
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from Google Docs",
    expected_paths=("/drive/v3/files",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]

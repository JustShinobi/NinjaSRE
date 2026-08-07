"""GitHub, end to end: capability, client, proxy, injection, vendor.

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


CHANGE_STATISTICS: Final = IntegrationScenario(
    key="github-change-statistics",
    integration="github",
    capability="github_change_statistics",
    arguments={
        "repository": "repo:acme/checkout",
        "start": "",
        "end": "",
        "group_by": "commit.author.name",
    },
    responses=(
        json_response(
            {
                "items": [
                    {
                        "sha": "a1",
                        "commit": {"author": {"name": "ana"}, "message": "raise cart limit"},
                    },
                    {"sha": "a2", "commit": {"author": {"name": "ana"}, "message": "bump deps"}},
                    {"sha": "a3", "commit": {"author": {"name": "sam"}, "message": "fix typo"}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 commits across",
    expected_paths=("/search/commits",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="github-recent-changes",
    integration="github",
    capability="github_recent_changes",
    arguments={"repository": "repo:acme/checkout", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {"items": [{"number": 412, "title": "raise cart limit", "user": {"login": "ana"}}]}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from GitHub",
    expected_paths=("/search/issues",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (CHANGE_STATISTICS, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "CHANGE_STATISTICS", "RECENT_CHANGES"]

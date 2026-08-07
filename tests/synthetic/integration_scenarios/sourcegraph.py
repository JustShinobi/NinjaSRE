"""Sourcegraph, end to end: capability, client, proxy, injection, vendor.

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
    key="sourcegraph-change-statistics",
    integration="sourcegraph",
    capability="sourcegraph_change_statistics",
    arguments={"repository": "cart_limit", "start": "", "end": "", "group_by": "repository"},
    responses=(
        json_response(
            [
                {"repository": "acme/checkout", "path": "cart.py"},
                {"repository": "acme/checkout", "path": "limits.py"},
                {"repository": "acme/payments", "path": "cart.py"},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 commits across",
    expected_paths=("/.api/search/stream",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="sourcegraph-recent-changes",
    integration="sourcegraph",
    capability="sourcegraph_recent_changes",
    arguments={"repository": "cart_limit", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            [
                {
                    "repository": "acme/checkout",
                    "path": "cart.py",
                    "lineMatches": [{"preview": "CART_LIMIT = 50"}],
                }
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from Sourcegraph",
    expected_paths=("/.api/search/stream",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (CHANGE_STATISTICS, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "CHANGE_STATISTICS", "RECENT_CHANGES"]

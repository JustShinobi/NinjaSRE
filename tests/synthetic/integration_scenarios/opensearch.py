"""OpenSearch, end to end: capability, client, proxy, injection, vendor.

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
    "username": "ninjasre-scenario",
    "password": "ninjasre-scenario-secret",
}


LOG_STATISTICS: Final = IntegrationScenario(
    key="opensearch-log-statistics",
    integration="opensearch",
    capability="opensearch_log_statistics",
    arguments={
        "query": "service:checkout",
        "start": "",
        "end": "",
        "group_by": "_source.log.level",
    },
    responses=(
        json_response(
            {
                "hits": {
                    "hits": [
                        {"_source": {"log": {"level": "error"}}},
                        {"_source": {"log": {"level": "error"}}},
                        {"_source": {"log": {"level": "info"}}},
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 log lines across",
    expected_paths=("/_search",),
)


SAMPLE_LOGS: Final = IntegrationScenario(
    key="opensearch-sample-logs",
    integration="opensearch",
    capability="opensearch_sample_logs",
    arguments={"query": "service:checkout AND log.level:error", "start": "", "end": "", "limit": 5},
    responses=(
        json_response(
            {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "log": {"level": "error"},
                                "message": "cart serialiser out of memory",
                            }
                        }
                    ]
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 log lines from OpenSearch",
    expected_paths=("/_search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]

"""Elasticsearch, end to end: capability, client, proxy, injection, vendor.

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


LOG_STATISTICS: Final = IntegrationScenario(
    key="elasticsearch-log-statistics",
    integration="elasticsearch",
    capability="elasticsearch_log_statistics",
    arguments={
        "query": "service:checkout",
        "start": "now-1h",
        "end": "now",
        "group_by": "_source.log.level",
    },
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
                        },
                        {
                            "_source": {
                                "log": {"level": "error"},
                                "message": "cart serialiser out of memory",
                            }
                        },
                        {"_source": {"log": {"level": "info"}, "message": "checkout ok"}},
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
    key="elasticsearch-sample-logs",
    integration="elasticsearch",
    capability="elasticsearch_sample_logs",
    arguments={
        "query": "service:checkout AND log.level:error",
        "start": "now-1h",
        "end": "now",
        "limit": 5,
    },
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
    expected_summary="1 log lines from Elasticsearch",
    expected_paths=("/_search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LOG_STATISTICS, SAMPLE_LOGS)

__all__ = ["CREDENTIAL", "SCENARIOS", "LOG_STATISTICS", "SAMPLE_LOGS"]

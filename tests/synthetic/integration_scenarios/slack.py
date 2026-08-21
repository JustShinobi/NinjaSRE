"""Slack, end to end: capability, client, proxy, injection, vendor.

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


RECENT_MESSAGES: Final = IntegrationScenario(
    key="slack-recent-messages",
    integration="slack",
    capability="slack_recent_messages",
    arguments={
        "channel": "C123",
        "start": "1754499600.000000",
        "end": "1754503200.000000",
        "limit": 10,
    },
    responses=(
        json_response(
            {
                "messages": [
                    {"text": "cart is 500ing", "user": "U1"},
                    {"text": "rolling back", "user": "U2"},
                    {"text": "joined", "subtype": "channel_join", "user": "U3"},
                ],
                "response_metadata": {"next_cursor": ""},
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from Slack",
    expected_paths=("/api/conversations.history",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="slack-post-message",
    integration="slack",
    capability="slack_post_message",
    arguments={"channel": "C123", "text": "Investigation complete: cart serialiser out of memory."},
    responses=(json_response({"ok": True, "ts": "1754503600.000100", "channel": "C123"}),),
    credential=CREDENTIAL,
    expected_summary="Slack accepted the change",
    expected_paths=("/api/chat.postMessage",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

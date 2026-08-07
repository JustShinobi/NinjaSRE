"""Rocket.Chat, end to end: capability, client, proxy, injection, vendor.

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
    "user_id": "ninjasre-scenario-second-000000",
}


RECENT_MESSAGES: Final = IntegrationScenario(
    key="rocket_chat-recent-messages",
    integration="rocket_chat",
    capability="rocket_chat_recent_messages",
    arguments={
        "channel": "incidents",
        "start": "2026-08-07T11:00:00Z",
        "end": "2026-08-07T12:00:00Z",
        "limit": 10,
    },
    responses=(
        json_response(
            {
                "messages": [
                    {"_id": "1", "msg": "cart is 500ing"},
                    {"_id": "2", "msg": "rolling back"},
                    {"_id": "3", "msg": "", "t": "uj"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from Rocket.Chat",
    expected_paths=("/api/v1/channels.history",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="rocket_chat-post-message",
    integration="rocket_chat",
    capability="rocket_chat_post_message",
    arguments={
        "channel": "#incidents",
        "text": "Investigation complete: cart serialiser out of memory.",
    },
    responses=(json_response({"success": True, "message": {"_id": "4"}}),),
    credential=CREDENTIAL,
    expected_summary="Rocket.Chat accepted the change",
    expected_paths=("/api/v1/chat.postMessage",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

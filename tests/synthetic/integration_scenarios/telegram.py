"""Telegram, end to end: capability, client, proxy, injection, vendor.

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
    key="telegram-recent-messages",
    integration="telegram",
    capability="telegram_recent_messages",
    arguments={"channel": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "result": [
                    {"update_id": 1, "message": {"chat": {"type": "group"}}},
                    {"update_id": 2, "message": {"chat": {"type": "group"}}},
                    {"update_id": 3, "message": {"chat": {"type": "private"}}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from Telegram",
    expected_paths=("/botninjasre-scenario-token-000000/getUpdates",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="telegram-post-message",
    integration="telegram",
    capability="telegram_post_message",
    arguments={
        "channel": "-1001234567890",
        "text": "Investigation complete: cart serialiser out of memory.",
    },
    responses=(json_response({"ok": True, "result": {"message_id": 42}}),),
    credential=CREDENTIAL,
    expected_summary="Telegram accepted the change",
    expected_paths=("/botninjasre-scenario-token-000000/sendMessage",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

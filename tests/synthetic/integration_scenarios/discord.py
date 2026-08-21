"""Discord, end to end: capability, client, proxy, injection, vendor.

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
    "channel_id": "123456789012345678",
}


RECENT_MESSAGES: Final = IntegrationScenario(
    key="discord-recent-messages",
    integration="discord",
    capability="discord_recent_messages",
    arguments={"channel": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            [
                {"id": "1", "type": 0, "content": "cart is 500ing"},
                {"id": "2", "type": 0, "content": "rolling back"},
                {"id": "3", "type": 7, "content": ""},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from Discord",
    expected_paths=("/api/v10/channels/123456789012345678/messages",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="discord-post-message",
    integration="discord",
    capability="discord_post_message",
    arguments={"channel": "", "text": "Investigation complete: cart serialiser out of memory."},
    responses=(json_response({"id": "4", "type": 0, "content": "Investigation complete"}),),
    credential=CREDENTIAL,
    expected_summary="Discord accepted the change",
    expected_paths=("/api/v10/channels/123456789012345678/messages",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

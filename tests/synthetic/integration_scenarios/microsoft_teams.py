"""Microsoft Teams, end to end: capability, client, proxy, injection, vendor.

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
    "team_id": "00000000-0000-0000-0000-000000000000",
}


RECENT_MESSAGES: Final = IntegrationScenario(
    key="microsoft_teams-recent-messages",
    integration="microsoft_teams",
    capability="microsoft_teams_recent_messages",
    arguments={"channel": "19:abc", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "value": [
                    {"id": "1", "messageType": "message"},
                    {"id": "2", "messageType": "message"},
                    {"id": "3", "messageType": "systemEventMessage"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from Microsoft Teams",
    expected_paths=("/v1.0/teams/00000000-0000-0000-0000-000000000000/channels/messages",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="microsoft_teams-post-message",
    integration="microsoft_teams",
    capability="microsoft_teams_post_message",
    arguments={
        "channel": "19:abc",
        "text": "Investigation complete: cart serialiser out of memory.",
    },
    responses=(json_response({"id": "4", "messageType": "message"}),),
    credential=CREDENTIAL,
    expected_summary="Microsoft Teams accepted the change",
    expected_paths=("/v1.0/teams/00000000-0000-0000-0000-000000000000/channels/messages",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

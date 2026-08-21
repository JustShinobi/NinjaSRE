"""Twilio, end to end: capability, client, proxy, injection, vendor.

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
    "account_sid": "AC00000000000000000000000000000000",
}


RECENT_MESSAGES: Final = IntegrationScenario(
    key="twilio-recent-messages",
    integration="twilio",
    capability="twilio_recent_messages",
    arguments={"channel": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "messages": [
                    {"sid": "SM1", "status": "delivered"},
                    {"sid": "SM2", "status": "delivered"},
                    {"sid": "SM3", "status": "failed"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from Twilio",
    expected_paths=("/2010-04-01/Accounts/AC00000000000000000000000000000000/Messages.json",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="twilio-post-message",
    integration="twilio",
    capability="twilio_post_message",
    arguments={
        "channel": "+447700900000",
        "text": "Investigation complete: cart serialiser out of memory.",
    },
    responses=(json_response({"sid": "SM4", "status": "queued"}),),
    credential=CREDENTIAL,
    expected_summary="Twilio accepted the change",
    expected_paths=("/2010-04-01/Accounts/AC00000000000000000000000000000000/Messages.json",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

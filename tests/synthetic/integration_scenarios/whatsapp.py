"""WhatsApp, end to end: capability, client, proxy, injection, vendor.

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
    "phone_number_id": "100000000000000",
}


RECENT_MESSAGES: Final = IntegrationScenario(
    key="whatsapp-recent-messages",
    integration="whatsapp",
    capability="whatsapp_recent_messages",
    arguments={"channel": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "data": [
                    {"name": "incident_update", "status": "APPROVED"},
                    {"name": "incident_resolved", "status": "APPROVED"},
                    {"name": "draft", "status": "PENDING"},
                ],
                "paging": {"cursors": {"after": ""}},
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 messages from WhatsApp",
    expected_paths=("/v21.0/100000000000000/message_templates",),
)


POST_MESSAGE: Final = IntegrationScenario(
    key="whatsapp-post-message",
    integration="whatsapp",
    capability="whatsapp_post_message",
    arguments={
        "channel": "447700900000",
        "text": "Investigation complete: cart serialiser out of memory.",
    },
    responses=(json_response({"messages": [{"id": "wamid.1"}]}),),
    credential=CREDENTIAL,
    expected_summary="WhatsApp accepted the change",
    expected_paths=("/v21.0/100000000000000/messages",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RECENT_MESSAGES, POST_MESSAGE)

__all__ = ["CREDENTIAL", "SCENARIOS", "RECENT_MESSAGES", "POST_MESSAGE"]

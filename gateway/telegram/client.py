"""The Bot API calls this surface makes, and the choice between polling and webhook.

Telegram offers two ways to receive updates and they are mutually exclusive:
long polling pulls with ``getUpdates``, a webhook is pushed to a URL that has to
be registered first, and registering one stops the other working. So the mode is
chosen once, from configuration, and setting a webhook explicitly
deletes it when the deployment switches back — a half-configured bot that
receives nothing is the failure mode this avoids.

**Polling advances an offset.** ``getUpdates`` redelivers everything until the
offset moves past it, so the offset is the acknowledgement, and it advances only
after an update has been handed to the caller.

There is no token in this module and no parameter that could hold one: the bot
token is injected by the credential proxy at the network edge, which is also why
the paths here are plain method names rather than the ``/bot<token>/method``
shape Telegram documents.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from gateway.chat.port import ChatTransport, PlatformCall, PlatformReply

#: The integration name the credential proxy resolves the bot token under.
TELEGRAM_INTEGRATION: Final = "telegram"

#: How long ``getUpdates`` waits for something to happen before answering empty.
#: Long polling: a short timeout is a busy loop, and a very long one delays a
#: clean shutdown by exactly its own length.
LONG_POLL_SECONDS: Final = 25

#: Updates fetched per poll. Bounded so a backlog after an outage is drained in
#: batches rather than in one response nothing can hold.
UPDATE_BATCH: Final = 100


class TelegramIngressMode(StrEnum):
    """How this deployment receives Telegram updates."""

    POLLING = "polling"
    WEBHOOK = "webhook"


@dataclass(slots=True)
class TelegramApi:
    """The Bot API, as the calls this surface actually makes."""

    transport: ChatTransport
    #: The next update to ask for. Telegram's acknowledgement mechanism, so it
    #: lives with the client rather than with whoever is looping.
    offset: int = field(default=0)

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        thread_id: str = "",
        reply_markup: Mapping[str, Any] | None = None,
    ) -> PlatformReply:
        """Post a message, in a forum topic when ``thread_id`` is given."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if thread_id:
            payload["message_thread_id"] = thread_id
        if reply_markup is not None:
            payload["reply_markup"] = dict(reply_markup)
        return await self.transport.send(
            PlatformCall(method="POST", path="sendMessage", payload=payload)
        )

    async def edit_message_text(
        self,
        *,
        chat_id: str,
        message_id: str,
        text: str,
        reply_markup: Mapping[str, Any] | None = None,
    ) -> PlatformReply:
        """Rewrite a message in place, which is how progress streams."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            # Always sent, even empty: Telegram keeps the old keyboard when the
            # field is absent, so a decided approval would keep its buttons.
            "reply_markup": dict(reply_markup or {"inline_keyboard": []}),
        }
        return await self.transport.send(
            PlatformCall(method="POST", path="editMessageText", payload=payload)
        )

    async def send_document(
        self, *, chat_id: str, thread_id: str, filename: str, content: str, caption: str = ""
    ) -> PlatformReply:
        """Deliver a long report as a file rather than as a wall of messages."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "document": {"filename": filename, "content": content},
            "caption": caption or filename,
        }
        if thread_id:
            payload["message_thread_id"] = thread_id
        return await self.transport.send(
            PlatformCall(method="POST", path="sendDocument", payload=payload)
        )

    async def answer_callback_query(
        self, *, callback_query_id: str, text: str = ""
    ) -> PlatformReply:
        """Acknowledge a button press, which is what stops the client spinning."""
        return await self.transport.send(
            PlatformCall(
                method="POST",
                path="answerCallbackQuery",
                payload={"callback_query_id": callback_query_id, "text": text},
            )
        )

    async def set_my_commands(self, commands: Sequence[Mapping[str, Any]]) -> PlatformReply:
        """Register the shared catalogue as this bot's command list."""
        return await self.transport.send(
            PlatformCall(method="POST", path="setMyCommands", payload={"commands": list(commands)})
        )

    # -- receiving --------------------------------------------------------------

    async def get_updates(self) -> tuple[Mapping[str, Any], ...]:
        """Return the next batch of updates, advancing the offset past them.

        The offset advances only after the batch has been returned, so an update
        the caller never received is redelivered rather than skipped.
        """
        reply = await self.transport.send(
            PlatformCall(
                method="POST",
                path="getUpdates",
                payload={
                    "offset": self.offset,
                    "limit": UPDATE_BATCH,
                    "timeout": LONG_POLL_SECONDS,
                },
            )
        )
        raw = reply.document.get("result")
        if not isinstance(raw, list):
            return ()
        updates = tuple(update for update in raw if isinstance(update, Mapping))
        if updates:
            self.offset = max(int(update.get("update_id", 0)) for update in updates) + 1
        return updates

    async def set_webhook(
        self, url: str, *, secret_token_configured: bool = False
    ) -> PlatformReply:
        """Register ``url`` as where updates are pushed.

        ``secret_token_configured`` says whether the deployment gave the proxy a
        secret to send as ``X-Telegram-Bot-Api-Secret-Token``. The value itself
        never passes through here — this only records that verification is
        expected, so an unverifiable webhook is a configuration error rather
        than an open endpoint.
        """
        payload: dict[str, Any] = {"url": url, "drop_pending_updates": False}
        if secret_token_configured:
            payload["secret_token_expected"] = True
        return await self.transport.send(
            PlatformCall(method="POST", path="setWebhook", payload=payload)
        )

    async def delete_webhook(self) -> PlatformReply:
        """Unregister the webhook, which is what makes polling work again."""
        return await self.transport.send(
            PlatformCall(method="POST", path="deleteWebhook", payload={})
        )


def message_id_of(reply: PlatformReply) -> str:
    """Return the message id a Telegram reply carries."""
    result = reply.document.get("result")
    if isinstance(result, Mapping):
        return str(result.get("message_id", ""))
    return ""


__all__ = [
    "LONG_POLL_SECONDS",
    "TELEGRAM_INTEGRATION",
    "UPDATE_BATCH",
    "TelegramApi",
    "TelegramIngressMode",
    "message_id_of",
]

"""What an inbound message means, and which thread a run belongs to.

Every platform produces the same four situations and no adapter decides between
them: a mention starts an investigation, a message in a thread that already has
one becomes mid-run context, a command is a command, and everything else is not
addressed to this bot at all. Putting that classification here rather than four
times is the difference between a rule and a coincidence.

**The binding is thread-to-run and it is the whole of the state.** A thread with
a run in it follows the conversation without needing to be re-tagged; a channel
without one ignores traffic. Both properties come from one lookup, which is why
there is no second place to ask "is this bot listening here".

**A run's chat surface is only what an operator routed.** The dispatcher refuses
an unrouted channel rather than defaulting to a team, for the same
reason an unknown node denies rather than resolving at the root.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from gateway.chat.commands import ChatCommand, find
from gateway.chat.identity import IdentityResolver, UnmappedChatUser
from gateway.chat.port import ChatTarget, InboundMessage, PlatformUser
from gateway.chat.routing import RoutingTable, UnroutedChannel
from platform.identity.errors import PermissionDenied
from platform.identity.permissions import Permission
from platform.observability.logging import get_logger

logger = get_logger(__name__)


class SessionAction(StrEnum):
    """What an inbound message asks for."""

    START_INVESTIGATION = "start_investigation"
    ADD_CONTEXT = "add_context"
    RUN_COMMAND = "run_command"
    IGNORE = "ignore"


@dataclass(slots=True)
class Bindings:
    """Which run each thread is carrying, and nothing else.

    Keyed on the *thread*, not the channel: one channel routinely carries three
    incidents at once, and a channel-keyed binding would feed all three into
    whichever run started last.
    """

    _runs: dict[str, str] = field(default_factory=dict)
    _targets: dict[str, ChatTarget] = field(default_factory=dict)

    def bind(self, target: ChatTarget, run_id: str) -> ChatTarget:
        """Record that ``target``'s thread is carrying ``run_id``, and return it."""
        if not target.is_threaded:
            raise ValueError(
                f"{target.platform} channel {target.channel_id!r} was bound without a thread. "
                f"An investigation runs in a thread, or a busy channel becomes unreadable."
            )
        self._runs[target.key] = run_id
        self._targets[run_id] = target
        return target

    def run_of(self, target: ChatTarget) -> str:
        """Return the run ``target``'s thread is carrying, or the empty string."""
        return self._runs.get(target.key, "")

    def target_of(self, run_id: str) -> ChatTarget | None:
        """Return the thread ``run_id`` is running in, if it started in chat."""
        return self._targets.get(run_id)

    def release(self, target: ChatTarget) -> str:
        """Forget ``target``'s binding and return the run it was carrying."""
        run_id = self._runs.pop(target.key, "")
        self._targets.pop(run_id, None)
        return run_id

    def __len__(self) -> int:
        return len(self._runs)


@runtime_checkable
class ChatRuntime(Protocol):
    """Everything the chat surface asks a deployment to actually do.

    A protocol for the reason ``gateway/http/services.py``'s ``InvestigationRunner``
    is one: composing a runtime — the LLM client, the capability catalogue, the
    credential proxy — is a deployment concern, and a chat adapter that composed
    one would be a second composition root nobody asked for.
    """

    async def start_investigation(
        self, *, objective: str, team_id: str, principal_id: str, context: Mapping[str, str]
    ) -> str:
        """Start an investigation and return its run identifier."""

    async def add_context(self, *, run_id: str, text: str, principal_id: str) -> None:
        """Queue ``text`` for delivery on ``run_id``'s next turn."""

    async def cancel(self, *, run_id: str, principal_id: str) -> None:
        """Ask ``run_id`` to stop at its next safe point."""


@dataclass(frozen=True, slots=True)
class Dispatch:
    """What the dispatcher decided, and everything the caller needs to act on it."""

    action: SessionAction
    message: InboundMessage
    run_id: str = ""
    command: ChatCommand | None = None
    refusal: str = ""

    @property
    def refused(self) -> bool:
        """Return whether this was refused rather than dispatched."""
        return bool(self.refusal)


@dataclass(slots=True)
class ChatDispatcher:
    """Turns an inbound message into the one thing it means.

    Classification is separate from authorisation on purpose: ``classify``
    answers "what is this", which every platform's tests assert directly, and
    ``dispatch`` adds "may they", which needs a directory and a routing table.
    """

    bindings: Bindings = field(default_factory=Bindings)
    routing: RoutingTable | None = None
    identities: IdentityResolver | None = None

    def classify(self, message: InboundMessage) -> SessionAction:
        """Return what ``message`` asks for, from its shape and the bindings alone."""
        if message.is_command:
            return SessionAction.RUN_COMMAND
        if self.bindings.run_of(message.target):
            return SessionAction.ADD_CONTEXT
        if message.addressed:
            return SessionAction.START_INVESTIGATION
        return SessionAction.IGNORE

    async def dispatch(self, message: InboundMessage) -> Dispatch:
        """Return what to do with ``message``, refusing what may not be done.

        Never raises for a refusal. A chat surface that raised on an unmapped
        user would turn "you are not mapped" into a stack trace in a log and
        silence in the channel — and a refusal nobody can see is a refusal
        nobody can act on.
        """
        action = self.classify(message)
        if action is SessionAction.IGNORE:
            return Dispatch(action=action, message=message)

        unrouted = self._unrouted(message.target)
        if unrouted:
            return Dispatch(action=SessionAction.IGNORE, message=message, refusal=unrouted)

        command = find(message.command) if message.is_command else None
        refusal = await self._authorise(message, action, command)
        if refusal:
            return Dispatch(action=action, message=message, command=command, refusal=refusal)

        return Dispatch(
            action=action,
            message=message,
            run_id=self.bindings.run_of(message.target),
            command=command,
        )

    def _unrouted(self, target: ChatTarget) -> str:
        """Return why ``target`` is not served, or the empty string."""
        if self.routing is None:
            return ""
        try:
            self.routing.team_of(target)
        except UnroutedChannel as unrouted:
            logger.info(
                "chat.unrouted_channel",
                platform=target.platform,
                channel_id=target.channel_id,
            )
            return str(unrouted)
        return ""

    async def _authorise(
        self, message: InboundMessage, action: SessionAction, command: ChatCommand | None
    ) -> str:
        """Return why ``message``'s author may not do this, or the empty string."""
        if self.identities is None:
            return ""
        needed = _permission_for(action, command)
        if needed is None:
            return ""
        try:
            await self.identities.authorise(message.user, needed)
        except UnmappedChatUser as unmapped:
            return str(unmapped)
        except PermissionDenied as denied:
            return str(denied)
        return ""

    def team_for(self, target: ChatTarget) -> str:
        """Return the team ``target`` serves, or the empty string when unrouted."""
        if self.routing is None:
            return ""
        route = self.routing.find(target)
        return route.team_id if route is not None else ""


def _permission_for(action: SessionAction, command: ChatCommand | None) -> Permission | None:
    """Return the permission ``action`` needs, from the catalogue where there is one.

    Starting a run and adding context to one are both ``investigate``: the
    second is guidance a run acts on, so somebody who may not start one must not
    be able to steer one either.
    """
    if command is not None:
        return command.requires
    if action in {SessionAction.START_INVESTIGATION, SessionAction.ADD_CONTEXT}:
        investigate = find("investigate")
        return investigate.requires if investigate else None
    return None


def user_key(user: PlatformUser) -> str:
    """Return the identifier a binding or an identity looks ``user`` up by."""
    return user.key


__all__ = [
    "Bindings",
    "ChatDispatcher",
    "ChatRuntime",
    "Dispatch",
    "SessionAction",
]

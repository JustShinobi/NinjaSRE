"""The ten behaviours every adapter satisfies, as data rather than as prose.

A four-platform contract is only worth having if adding a fifth platform makes
the build fail until the fifth adapter satisfies it. That needs the contract to
be enumerable at runtime — a list a test parameterises over — rather than a
section of a document somebody remembers to reread.

So each behaviour is a row here carrying what it requires of a platform, and
``tests/contract/chat/`` runs every row against every registered adapter. A
behaviour added here without an adapter change fails four tests, which is the
intended cost. A platform registered without an adapter fails ten.

**Why the rows name capabilities rather than assertions.** The assertion lives
in the test, where it can drive a fake transport and inspect what was posted.
What lives here is the *statement*: this behaviour exists, it is required of
everybody, and it is the reason these methods are on the port. Splitting it that
way is what stops production code from importing a test harness.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from config.constants.surfaces import CHAT_PLATFORMS


@dataclass(frozen=True, slots=True)
class ChatBehaviour:
    """One thing every adapter must do, and what doing it requires."""

    name: str
    #: What the suite asserts, in the words the plan's table uses.
    assertion: str
    #: The ``ChatPlatform`` members this behaviour exercises. A platform missing
    #: one of these cannot satisfy the behaviour, and saying so at registration
    #: is cheaper than a failure inside an assertion about posted text.
    requires: tuple[str, ...]


#: The plan's table, in order. The order is the order a run uses them, which is
#: also the order a reader of a failing suite finds most useful.
CHAT_CONTRACT: Final[tuple[ChatBehaviour, ...]] = (
    ChatBehaviour(
        name="start_by_mention_or_command",
        assertion="an investigation begins bound to a thread",
        requires=("parse_message", "post"),
    ),
    ChatBehaviour(
        name="stream_progress",
        assertion="updates edit one message in place, within the platform's rate limit",
        requires=("post", "edit", "limits"),
    ),
    ChatBehaviour(
        name="deliver_report",
        assertion="the whole report arrives, split or attached if it is oversized",
        requires=("post", "attach", "limits"),
    ),
    ChatBehaviour(
        name="render_approval",
        assertion="target, proposed change, blast radius, and rollback plan are all present",
        requires=("render_interaction", "send_interaction"),
    ),
    ChatBehaviour(
        name="resolve_interaction",
        assertion="a decision reaches the core and closes the element here",
        requires=("parse_decision", "close_interaction"),
    ),
    ChatBehaviour(
        name="add_mid_run_context",
        assertion="a message in a bound thread becomes queued guidance",
        requires=("parse_message",),
    ),
    ChatBehaviour(
        name="map_identity",
        assertion="a platform user resolves to a principal, or is refused",
        requires=("user_of",),
    ),
    ChatBehaviour(
        name="refuse_unmapped",
        assertion="a privileged action by an unmapped user is denied, with instructions",
        requires=("user_of", "post"),
    ),
    ChatBehaviour(
        name="sanitise_errors",
        assertion="no message carries exception detail",
        requires=("post",),
    ),
    ChatBehaviour(
        name="survive_disconnect",
        assertion="the run continues and the report is delivered on reconnect or elsewhere",
        requires=("post", "edit"),
    ),
)

#: Every behaviour by name, for a test that wants one row.
CHAT_BEHAVIOURS: Final[dict[str, ChatBehaviour]] = {
    behaviour.name: behaviour for behaviour in CHAT_CONTRACT
}


def required_members() -> tuple[str, ...]:
    """Return every ``ChatPlatform`` member the contract exercises, sorted."""
    return tuple(sorted({member for row in CHAT_CONTRACT for member in row.requires}))


def missing_members(platform: object) -> tuple[str, ...]:
    """Return the contract's required members ``platform`` does not have.

    Checked by name rather than with ``isinstance`` against the protocol: a
    ``runtime_checkable`` protocol only checks that the attributes exist, and
    reporting *which* one is absent is the difference between a fixable failure
    and "does not satisfy ChatPlatform".
    """
    return tuple(member for member in required_members() if not hasattr(platform, member))


def unimplemented_platforms(implemented: Sequence[str]) -> tuple[str, ...]:
    """Return the configured platforms ``implemented`` does not cover.

    "All four platforms pass the same suite" decays in one specific way: a
    fifth platform is added to the constant while the suite keeps parameterising
    over the four that already have adapters.
    """
    covered = set(implemented)
    return tuple(name for name in CHAT_PLATFORMS if name not in covered)


__all__ = [
    "CHAT_BEHAVIOURS",
    "CHAT_CONTRACT",
    "ChatBehaviour",
    "missing_members",
    "required_members",
    "unimplemented_platforms",
]

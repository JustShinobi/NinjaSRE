"""Slack user to NinjaSRE principal, and the workspace that scopes the lookup.

A Slack user id is unique inside a workspace and nowhere else, so the mapping is
keyed on both. A directory keyed on the user id alone would let ``U0123`` in a
workspace nobody configured resolve to a principal in the one that was — which
is the exact shape of the mistake this module exists to make impossible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from config.constants.surfaces import CHAT_PLATFORM_SLACK
from gateway.chat.identity import ChatIdentity, MappingIdentityDirectory
from gateway.chat.port import PlatformUser
from platform.identity.permissions import Role


def slack_user(user_id: str, *, team_id: str, display_name: str = "") -> PlatformUser:
    """Return the platform user a Slack id in ``team_id`` names."""
    return PlatformUser(
        platform=CHAT_PLATFORM_SLACK,
        user_id=user_id,
        display_name=display_name,
        workspace_id=team_id,
    )


def slack_identity(
    *,
    user_id: str,
    team_id: str,
    principal_id: str,
    node_id: str = "",
    display_name: str = "",
) -> ChatIdentity:
    """Return the mapping row for one Slack user."""
    return ChatIdentity(
        platform=CHAT_PLATFORM_SLACK,
        platform_user_id=user_id,
        workspace_id=team_id,
        principal_id=principal_id,
        node_id=node_id,
        display_name=display_name,
    )


def directory_of(
    rows: Sequence[Mapping[str, str]], roles: Mapping[str, Role]
) -> MappingIdentityDirectory:
    """Return the Slack directory a deployment's configured rows describe.

    Every row is stamped with this platform rather than trusting the file to say
    so: a Slack mapping file that named ``discord`` would silently map nobody,
    and "nobody is mapped" is indistinguishable from "nothing is configured".
    """
    return MappingIdentityDirectory(
        identities=tuple(
            slack_identity(
                user_id=str(row["user_id"]),
                team_id=str(row.get("team_id", "")),
                principal_id=str(row["principal_id"]),
                node_id=str(row.get("node_id", "")),
                display_name=str(row.get("display_name", "")),
            )
            for row in rows
        ),
        roles=dict(roles),
    )


__all__ = [
    "directory_of",
    "slack_identity",
    "slack_user",
]

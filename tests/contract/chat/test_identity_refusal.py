"""An unmapped chat user cannot perform a privileged action, on any platform.

Auto-provisioning is deliberately absent, so the interesting case is not "the
mapping is wrong" but "there is no mapping", which is the normal state of every
person in a workspace who has never been granted anything. They must be refused,
and the refusal has to say how to stop being refused — a denial nobody can act
on becomes a support ticket.
"""

from __future__ import annotations

import pytest

from gateway.chat.identity import (
    ChatIdentity,
    IdentityResolver,
    MappingIdentityDirectory,
    UnmappedChatUser,
    refusal_message,
)
from gateway.chat.port import ChatPlatform, PlatformUser
from platform.identity.errors import PermissionDenied
from platform.identity.permissions import Permission, Role
from tests.contract.chat.conftest import Adapter

pytestmark = pytest.mark.contract


def _directory(known: PlatformUser, *, role: Role) -> MappingIdentityDirectory:
    """Return a directory that knows ``known`` and nobody else.

    Built from the user the adapter actually parsed rather than from a table of
    identifiers written here. The four platforms scope a user differently —
    Slack by workspace, Teams by tenant, Telegram and Discord by chat and guild
    — and a directory keyed on a hand-written guess would test the guess.
    """
    return MappingIdentityDirectory(
        identities=(
            ChatIdentity(
                platform=known.platform,
                platform_user_id=known.user_id,
                workspace_id=known.workspace_id,
                principal_id="ada",
                node_id="payments",
                display_name="Ada",
            ),
        ),
        roles={"ada": role},
    )


def _stranger(known: PlatformUser, user_id: str = "somebody-else") -> PlatformUser:
    """Return somebody in the same place as ``known`` that nobody has mapped."""
    return PlatformUser(
        platform=known.platform,
        user_id=user_id,
        display_name="Stranger",
        workspace_id=known.workspace_id,
    )


async def test_a_mapped_user_resolves_to_a_principal(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    user = platform.user_of(adapter.mention())
    assert user is not None

    resolver = IdentityResolver(directory=_directory(user, role=Role.RESPONDER))
    identity = await resolver.resolve(user)

    assert identity.principal_id == "ada"
    assert identity.node_id == "payments"


async def test_an_unmapped_user_is_refused_a_privileged_action(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    user = platform.user_of(adapter.mention())
    assert user is not None

    resolver = IdentityResolver(directory=_directory(user, role=Role.RESPONDER))

    with pytest.raises(UnmappedChatUser) as refused:
        await resolver.authorise(_stranger(user), Permission.REMEDIATION_APPROVE)

    assert "somebody-else" in str(refused.value)


async def test_the_refusal_says_how_to_be_granted_access(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    user = platform.user_of(adapter.mention())
    assert user is not None

    message = refusal_message(_stranger(user, "nobody"), Permission.REMEDIATION_APPROVE)

    assert "nobody" in message
    assert Permission.REMEDIATION_APPROVE.value in message
    # Actionable: it names the platform, the identifier an operator has to map,
    # and the role that would have been enough.
    assert adapter.platform in message
    assert "responder" in message


async def test_a_mapped_user_without_the_permission_is_denied_rather_than_unmapped(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    """Two different failures, because they lead to two different next actions."""
    user = platform.user_of(adapter.mention())
    assert user is not None

    resolver = IdentityResolver(directory=_directory(user, role=Role.VIEWER))

    with pytest.raises(PermissionDenied):
        await resolver.authorise(user, Permission.REMEDIATION_APPROVE)


async def test_an_unmapped_user_may_still_read_where_that_is_configured(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    """The plan's flowchart: unmapped plus non-privileged is a permitted read."""
    user = platform.user_of(adapter.mention())
    assert user is not None
    stranger = _stranger(user, "nobody")

    resolver = IdentityResolver(
        directory=_directory(user, role=Role.RESPONDER), anonymous_reads=True
    )

    assert await resolver.may(stranger, Permission.INVESTIGATION_READ) is True
    assert await resolver.may(stranger, Permission.REMEDIATION_APPROVE) is False


async def test_anonymous_reads_are_off_unless_a_deployment_turns_them_on(
    adapter: Adapter, platform: ChatPlatform
) -> None:
    user = platform.user_of(adapter.mention())
    assert user is not None

    resolver = IdentityResolver(directory=_directory(user, role=Role.RESPONDER))

    assert await resolver.may(_stranger(user, "nobody"), Permission.INVESTIGATION_READ) is False

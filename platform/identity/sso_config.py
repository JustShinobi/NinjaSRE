"""The provider an operator points NinjaSRE at, and the mapping it produces.

**A configuration cannot go live until it has been tested**. That is
not a nicety. SSO is the path every human uses, so a misconfiguration is not a
degraded feature — it is every operator locked out of the tool they would use to
fix it, during whatever incident prompted the change. ``activate`` therefore
refuses a configuration whose test has not passed, and a test result is bound to
the exact settings it was produced from: editing anything invalidates it.

**Group mapping always produces an answer**. A provider that
returns no groups, or groups nobody has mapped, resolves to the default team and
the fallback is recorded. Refusing the sign-in instead would mean a directory
change nobody made deliberately becomes an outage.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from config.constants.security import (
    OIDC_DEFAULT_SCOPES,
    OIDC_EMAIL_CLAIM,
    OIDC_GROUPS_CLAIM,
    OIDC_NAME_CLAIM,
    OIDC_SUBJECT_CLAIM,
)
from platform.identity.errors import SsoConfigInvalid, SsoNotVerified


@dataclass(frozen=True, slots=True)
class ClaimMapping:
    """Which claim carries which fact.

    Overridable because "groups" is spelled at least four ways across the
    providers operators actually run, and a deployment that has to patch the
    platform to read its own directory is a deployment that forks it.
    """

    subject: str = OIDC_SUBJECT_CLAIM
    email: str = OIDC_EMAIL_CLAIM
    display_name: str = OIDC_NAME_CLAIM
    groups: str = OIDC_GROUPS_CLAIM


@dataclass(frozen=True, slots=True)
class SsoConfig:
    """One organisation's identity provider, and how its groups become teams.

    ``fingerprint`` is what binds a test result to the settings it was produced
    from. Anything that could change the outcome of a sign-in is in it; anything
    cosmetic is not.
    """

    provider: str
    issuer: str
    client_id: str
    authorisation_endpoint: str
    token_endpoint: str
    jwks_uri: str
    redirect_uri: str
    scopes: tuple[str, ...] = OIDC_DEFAULT_SCOPES
    claims: ClaimMapping = field(default_factory=ClaimMapping)
    #: Provider group name to node id. A group naming no node is ignored, which
    #: is what lets a directory carry groups this deployment does not care about.
    group_to_node: Mapping[str, str] = field(default_factory=dict)
    #: Where a user with no mapped group lands. Required: without it,
    #: "no group claims" would have no answer but refusal.
    default_node_id: str | None = None
    is_active: bool = False

    def __post_init__(self) -> None:
        problems = list(self.problems())
        if problems:
            raise SsoConfigInvalid(problems)

    def problems(self) -> Iterable[str]:
        """Yield everything wrong with this configuration, in operator language."""
        for name, value in (
            ("provider", self.provider),
            ("issuer", self.issuer),
            ("client_id", self.client_id),
            ("authorisation_endpoint", self.authorisation_endpoint),
            ("token_endpoint", self.token_endpoint),
            ("jwks_uri", self.jwks_uri),
            ("redirect_uri", self.redirect_uri),
        ):
            if not value:
                yield f"{name} is required"
        for name, value in (
            ("issuer", self.issuer),
            ("authorisation_endpoint", self.authorisation_endpoint),
            ("token_endpoint", self.token_endpoint),
            ("jwks_uri", self.jwks_uri),
        ):
            if value and not value.startswith("https://"):
                yield f"{name} must be https: an identity flow over plain http is not one"
        if "openid" not in self.scopes:
            yield "the scopes must include 'openid', or the provider will not issue an id token"
        if self.default_node_id is None:
            yield (
                "default_node_id is required: a provider that returns no group claims has to "
                "map somewhere, and the alternative is refusing the sign-in"
            )

    @property
    def fingerprint(self) -> tuple[object, ...]:
        """Return what a test result is valid for.

        Everything that could change what a sign-in produces, and nothing else.
        A configuration whose fingerprint changed has not been tested, whatever
        the stored result says.
        """
        return (
            self.provider,
            self.issuer,
            self.client_id,
            self.authorisation_endpoint,
            self.token_endpoint,
            self.jwks_uri,
            self.redirect_uri,
            tuple(sorted(self.scopes)),
            self.claims,
            tuple(sorted(self.group_to_node.items())),
            self.default_node_id,
        )


@dataclass(frozen=True, slots=True)
class SsoTestResult:
    """What a test sign-in produced, and which settings produced it."""

    fingerprint: tuple[object, ...]
    succeeded: bool
    subject: str | None = None
    email: str | None = None
    groups: tuple[str, ...] = ()
    mapped_node_id: str | None = None
    used_default: bool = False
    problems: tuple[str, ...] = ()

    def covers(self, config: SsoConfig) -> bool:
        """Return whether this result was produced by ``config`` as it stands now."""
        return self.succeeded and self.fingerprint == config.fingerprint


@dataclass(frozen=True, slots=True)
class GroupMapping:
    """Where a sign-in put somebody, and whether it had to fall back."""

    node_id: str | None
    groups: tuple[str, ...]
    used_default: bool


def map_groups(config: SsoConfig, groups: Sequence[str]) -> GroupMapping:
    """Return the node ``groups`` map to, falling back to the default.

    The *first* mapped group wins, in the order the provider returned them.
    Deterministic, and it matches how directories order group membership — most
    specific first — which is the reading an operator expects when somebody is
    in two mapped groups.
    """
    for group in groups:
        node_id = config.group_to_node.get(group)
        if node_id is not None:
            return GroupMapping(node_id=node_id, groups=tuple(groups), used_default=False)
    return GroupMapping(node_id=config.default_node_id, groups=tuple(groups), used_default=True)


def activate(config: SsoConfig, result: SsoTestResult | None) -> SsoConfig:
    """Return ``config`` marked active, or raise ``SsoNotVerified``.

    Refuses on three counts, and they are the same refusal: there is no result,
    the result failed, or the result was produced by different settings. All
    three mean nobody has watched this configuration complete a sign-in.
    """
    if result is None or not result.covers(config):
        raise SsoNotVerified(config.provider)
    return replace(config, is_active=True)


def deactivate(config: SsoConfig) -> SsoConfig:
    """Return ``config`` marked inactive, so break-glass is the way in."""
    return replace(config, is_active=False)


__all__ = [
    "ClaimMapping",
    "GroupMapping",
    "SsoConfig",
    "SsoTestResult",
    "activate",
    "deactivate",
    "map_groups",
]

"""Single sign-on: configure it, test it, and only then let it be the way in.

**Activation is refused until a test has passed against the settings as they
stand.** That is not a nicety and it is the reason these four routes exist as
four rather than one. SSO is the path every human uses, so a misconfiguration is
not a degraded feature — it is every operator locked out of the tool they would
use to fix it, during whatever incident prompted the change.

The binding between a test and the settings that passed it is a **digest of the
settings themselves**, stored beside them. Editing anything produces a different
digest, so a stale test result cannot cover an edited document: the invalidation
is a property of the data rather than a rule somebody has to remember. A
cosmetic change that cannot affect a sign-in is not in the fingerprint, so
re-testing is not demanded for one.

**What the test proves, and what it does not.** It takes the claim set the
provider returns for a real test user and runs it through the same
``read_claims`` and ``map_groups`` a sign-in takes: the issuer matches, the
claim names are the ones this provider actually sends, a subject and an email
are present, and the groups map somewhere. It does *not* prove the endpoints are
reachable from this deployment — nothing here opens a socket. An operator who
can produce that claim set has already reached the provider, which is the part
that makes this the right trade: the test uses evidence the operator has rather
than a round trip a gateway cannot make on their behalf.

The settings live in the configuration tree rather than a store of their own,
which puts them under the same provenance, preview and audit as everything else
an operator changes. None of the fields is a secret; a client secret, when a
provider needs one, belongs in the vault and is not here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request
from gateway.http.state import GatewayState
from platform.config_service.errors import ConfigInvalid
from platform.config_service.schema.policies import SsoSettings
from platform.config_service.service import ConfigService
from platform.identity.errors import SsoConfigInvalid, SsoExchangeFailed, SsoNotVerified
from platform.identity.oidc import read_claims
from platform.identity.sso_config import ClaimMapping, SsoConfig, activate
from platform.persistence.ports.audit_repository import ActorKind
from platform.startup.bootstrap import organisation_id

router = APIRouter(prefix="/identity/sso", tags=["identity"])


class SsoClaimView(BaseModel):
    subject: str
    email: str
    display_name: str
    groups: str


class SsoView(BaseModel):
    """The configuration, and the two facts about it that decide what may happen."""

    provider: str = ""
    issuer: str = ""
    client_id: str = ""
    authorisation_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""
    redirect_uri: str = ""
    scopes: list[str] = Field(default_factory=list)
    claims: SsoClaimView
    group_to_node: dict[str, str] = Field(default_factory=dict)
    default_node_id: str = ""
    is_active: bool = False
    #: Whether a test has passed **against these settings**. Derived rather than
    #: stored as a flag, so it cannot be true of a document somebody has edited.
    verified: bool = False
    #: Everything wrong with the settings, in operator language. Empty when the
    #: configuration is one a sign-in could be attempted with.
    problems: list[str] = Field(default_factory=list)


class SsoWriteRequest(BaseModel):
    provider: str = ""
    issuer: str = ""
    client_id: str = ""
    authorisation_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""
    redirect_uri: str = ""
    scopes: list[str] = Field(default_factory=list)
    claims: SsoClaimView | None = None
    group_to_node: dict[str, str] = Field(default_factory=dict)
    default_node_id: str = ""


class SsoTestRequest(BaseModel):
    """The claim set the provider returned for a test user."""

    claims: dict[str, Any] = Field(default_factory=dict)


class SsoTestView(BaseModel):
    succeeded: bool
    subject: str = ""
    email: str = ""
    groups: list[str] = Field(default_factory=list)
    mapped_node_id: str = ""
    used_default: bool = False
    problems: list[str] = Field(default_factory=list)


def _service(state: GatewayState, auth: AuthenticatedRequest) -> ConfigService:
    return ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails)


def _node(auth: AuthenticatedRequest) -> str:
    """Return the node the identity provider is configured at.

    The organisation root, always. A directory is how *people* reach this
    deployment, and a per-team identity provider would mean somebody's ability
    to sign in depended on which team they were about to land in — which is
    circular.
    """
    return auth.scope.org_id or organisation_id()


def digest_of(settings: SsoSettings) -> str:
    """Return the digest a passing test is bound to.

    Everything that could change what a sign-in produces, and nothing else.
    ``is_active`` and the stored digest are excluded on purpose: activating a
    tested configuration must not invalidate the test that permitted it.
    """
    fingerprint = json.dumps(
        {
            "provider": settings.provider,
            "issuer": settings.issuer,
            "client_id": settings.client_id,
            "authorisation_endpoint": settings.authorisation_endpoint,
            "token_endpoint": settings.token_endpoint,
            "jwks_uri": settings.jwks_uri,
            "redirect_uri": settings.redirect_uri,
            "scopes": sorted(settings.scopes),
            "claims": {
                "subject": settings.claims.subject,
                "email": settings.claims.email,
                "display_name": settings.claims.display_name,
                "groups": settings.claims.groups,
            },
            "group_to_node": dict(sorted(settings.group_to_node.items())),
            "default_node_id": settings.default_node_id,
        },
        sort_keys=True,
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def _config_of(settings: SsoSettings) -> SsoConfig:
    """Return the platform's own configuration object, or raise naming the problems."""
    return SsoConfig(
        provider=settings.provider,
        issuer=settings.issuer,
        client_id=settings.client_id,
        authorisation_endpoint=settings.authorisation_endpoint,
        token_endpoint=settings.token_endpoint,
        jwks_uri=settings.jwks_uri,
        redirect_uri=settings.redirect_uri,
        scopes=tuple(settings.scopes),
        claims=ClaimMapping(
            subject=settings.claims.subject,
            email=settings.claims.email,
            display_name=settings.claims.display_name,
            groups=settings.claims.groups,
        ),
        group_to_node=dict(settings.group_to_node),
        default_node_id=settings.default_node_id or None,
        is_active=settings.is_active,
    )


def _problems(settings: SsoSettings) -> list[str]:
    """Return everything wrong with ``settings``, without raising."""
    try:
        _config_of(settings)
    except SsoConfigInvalid as invalid:
        return list(invalid.problems)
    return []


def _view(settings: SsoSettings) -> SsoView:
    return SsoView(
        provider=settings.provider,
        issuer=settings.issuer,
        client_id=settings.client_id,
        authorisation_endpoint=settings.authorisation_endpoint,
        token_endpoint=settings.token_endpoint,
        jwks_uri=settings.jwks_uri,
        redirect_uri=settings.redirect_uri,
        scopes=list(settings.scopes),
        claims=SsoClaimView(
            subject=settings.claims.subject,
            email=settings.claims.email,
            display_name=settings.claims.display_name,
            groups=settings.claims.groups,
        ),
        group_to_node=dict(settings.group_to_node),
        default_node_id=settings.default_node_id,
        is_active=settings.is_active,
        # Derived on every read. A flag would be a second answer to "has this
        # been tested", and the two would disagree the first time somebody
        # edited the document through another route.
        verified=(
            settings.verified_digest != "" and settings.verified_digest == digest_of(settings)
        ),
        problems=_problems(settings),
    )


async def _settings(state: GatewayState, auth: AuthenticatedRequest) -> SsoSettings:
    effective = await _service(state, auth).resolve(_node(auth))
    return effective.config.policies.sso


async def _write(
    state: GatewayState, auth: AuthenticatedRequest, patch: dict[str, Any]
) -> SsoSettings:
    """Apply ``patch`` under ``policies.sso`` and return what now applies."""
    service = _service(state, auth)
    try:
        await service.set_settings(
            _node(auth),
            {"policies": {"sso": patch}},
            actor_id=auth.principal_id,
            actor_kind=ActorKind.USER,
        )
    except ConfigInvalid as invalid:
        raise bad_request(str(invalid)) from invalid
    return (await service.resolve(_node(auth))).config.policies.sso


@router.get("", response_model=SsoView)
async def read_sso(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> SsoView:
    """Return the identity provider this deployment is pointed at."""
    return _view(await _settings(state, auth))


@router.put("", response_model=SsoView)
async def write_sso(
    body: SsoWriteRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> SsoView:
    """Replace the configuration, and drop any test result it invalidates.

    The digest is cleared explicitly as well as being invalidated by
    construction, so the *stored* document never carries a result that belongs
    to settings it no longer holds. Two mechanisms for one property, and the
    reason is that this is the property somebody gets locked out over.
    """
    return _view(
        await _write(
            state,
            auth,
            {
                "provider": body.provider,
                "issuer": body.issuer,
                "client_id": body.client_id,
                "authorisation_endpoint": body.authorisation_endpoint,
                "token_endpoint": body.token_endpoint,
                "jwks_uri": body.jwks_uri,
                "redirect_uri": body.redirect_uri,
                "scopes": list(body.scopes),
                **(
                    {}
                    if body.claims is None
                    else {
                        "claims": {
                            "subject": body.claims.subject,
                            "email": body.claims.email,
                            "display_name": body.claims.display_name,
                            "groups": body.claims.groups,
                        }
                    }
                ),
                "group_to_node": dict(body.group_to_node),
                "default_node_id": body.default_node_id,
                "is_active": False,
                "verified_digest": "",
            },
        )
    )


@router.post("/test", response_model=SsoTestView)
async def test_sso(
    body: SsoTestRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> SsoTestView:
    """Run a real claim set through the configuration, and record whether it worked.

    The result is stored as the digest of the settings it passed against, so it
    covers *these* settings and nothing else. A failure stores nothing, which
    leaves activation refused — the correct outcome, and the one that does not
    depend on anybody reading the response.
    """
    settings = await _settings(state, auth)
    problems = _problems(settings)
    if problems:
        return SsoTestView(succeeded=False, problems=problems)

    config = _config_of(settings)
    try:
        identity = read_claims(config, body.claims)
    except SsoExchangeFailed as failed:
        return SsoTestView(succeeded=False, problems=[str(failed)])

    await _write(state, auth, {"verified_digest": digest_of(settings)})
    return SsoTestView(
        succeeded=True,
        subject=identity.subject,
        email=identity.email,
        groups=list(identity.groups),
        mapped_node_id=identity.node_id or "",
        used_default=identity.used_default_team,
    )


@router.post("/activate", response_model=SsoView)
async def activate_sso(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> SsoView:
    """Make this provider the way in, refusing until a test has passed on it.

    Three refusals, and they are one refusal: there is no result, the settings
    are not usable, or the result was produced by different settings. All three
    mean nobody has watched this configuration complete a sign-in, and every one
    of them ends with an operator locked out.
    """
    settings = await _settings(state, auth)
    problems = _problems(settings)
    if problems:
        raise bad_request("; ".join(problems))

    config = _config_of(settings)
    if settings.verified_digest != digest_of(settings):
        raise bad_request(
            str(SsoNotVerified(config.provider))
            + " Run the test against these settings first: activating an untested "
            "identity provider is how every operator loses their way in."
        )

    try:
        activate(config, _passing_result(config))
    except SsoNotVerified as refused:  # pragma: no cover — the digest check is above
        raise bad_request(str(refused)) from refused

    return _view(await _write(state, auth, {"is_active": True}))


def _passing_result(config: SsoConfig) -> Any:
    """Return the platform's own result object for a test this route has verified.

    The digest above is what actually decides; this hands the platform's
    ``activate`` the shape it asks for so the refusal lives in one place rather
    than two. It is only ever constructed after the digest matched.
    """
    from platform.identity.sso_config import SsoTestResult

    return SsoTestResult(fingerprint=config.fingerprint, succeeded=True)


__all__ = ["digest_of", "router"]

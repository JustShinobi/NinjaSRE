"""The model providers this deployment can be pointed at, and whether one works.

Three routes, and the split between them is the whole design.

The two ``GET``s are free. They read the nine descriptors — what each provider is
called, which fields it needs, what it is known for — and join them to what this
deployment has in its vault. Nothing they do leaves the host, so a console can
render them on every page load and a first run can show the choice before
anything is configured.

``POST /{provider_id}/verify`` is not free. It exercises tool calling and
structured output against the operator's own endpoint, which costs them tokens,
so it is a ``POST`` an operator asks for rather than something a listing does on
their behalf. ``first_run.py`` records the same decision for the self-check, and
this keeps it: a page that spent money every time somebody opened it is a page
nobody opens twice.

**Configured and verified are separate facts and are never merged.** A key that
is present and a key that works are exactly the two states an operator is trying
to tell apart at three in the morning, and a listing that reported the first as
the second would be wrong in the one direction that matters.

Nothing here reads a credential. A descriptor says what to *ask for*; the value
goes in through ``PUT /v1/integrations/{name}/credential`` like any integration's
and comes back out through nothing at all.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config.constants.llm import SUPPORTED_PROVIDERS
from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from core.llm.onboarding import (
    ProviderOnboarding,
    UnknownProviderError,
    all_onboardings,
    credential_schema_for,
    onboarding_for,
    provider_names,
)
from core.llm.verification import ModelVerdict, verify_model
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.state import GatewayState
from gateway.http.verifications import record_check, recorded_checks
from platform.config_service.service import ConfigService
from platform.credentials.health import CredentialHealth
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.ports.verification_ledger import (
    VerificationRecord,
    VerificationSubject,
)

router = APIRouter(prefix="/v1/providers", tags=["providers"])

#: What the listing says about a provider nothing has been verified against.
#: Spelled out rather than left empty, because a blank cell reads as "fine" and
#: this state is the one an operator has to act on.
_NOT_VERIFIED = (
    "no verification has been run against this deployment — a stored credential "
    "is not the same fact as an endpoint that answers"
)

_NOT_CONFIGURED = "no credential is stored for this provider"


class CredentialFieldView(BaseModel):
    name: str
    label: str
    secret: bool
    required: bool
    help: str
    #: The variable an operator may set instead of entering a value. Served so
    #: a form can say "or set GOOGLE_API_KEY" rather than leaving somebody to
    #: guess that the two are the same credential.
    environment_variable: str = ""


class ProviderView(BaseModel):
    """One provider, its descriptor and this deployment's state for it.

    There is no field here a stored credential could be read back into, which is
    what lets the whole document be served to anyone who may read configuration.
    """

    provider_id: str
    display_name: str
    #: Whether this provider runs on the operator's own infrastructure. Reported
    #: for every provider rather than only the ones that do: a listing that
    #: marked only the local one would make "which of these leaves my
    #: infrastructure" a question about absence.
    local: bool
    configured: bool
    verified: bool
    default_model: str
    detail: str = ""


class ProviderList(BaseModel):
    providers: list[ProviderView]


class ProviderDetailView(ProviderView):
    """One provider in full: everything a form or a prompt needs to set it up."""

    fields: list[CredentialFieldView]
    guidance: str = ""
    where_to_get_it: str = ""
    models: list[str]
    install_hint: str = ""


class ProviderVerificationView(BaseModel):
    """What a real request to the provider's endpoint came back with.

    ``detail`` is the sentence — the working configuration when it passed, the
    limitation when it did not. Never "verification failed", which is a
    restatement rather than something anybody can act on.
    """

    provider_id: str
    verified: bool
    model_id: str
    detail: str
    remedy: str = ""
    #: The endpoint's other models that would satisfy the contract, where it
    #: could be asked. Empty when it could not, which is honest rather than
    #: encouraging.
    alternatives: list[str]


def _onboarding(provider_id: str) -> ProviderOnboarding:
    """Return the named provider's descriptor, or raise a 404 naming the nine.

    Raises:
        ApiProblem: no supported provider answers to that identifier.
    """
    try:
        return onboarding_for(provider_id)
    except UnknownProviderError as unknown:
        raise not_found(
            f"no supported provider named {provider_id!r}. This build supports: "
            f"{', '.join(provider_names())}"
        ) from unknown


async def _configured(state: GatewayState, auth: AuthenticatedRequest) -> frozenset[str]:
    """Return which providers this team has a usable credential for.

    Established by asking the vault rather than by reading configuration: a
    provider named in a settings document with nothing behind it is a provider
    that fails at the first request.
    """
    schemas = CredentialSchemaRegistry.from_schemas(
        *(credential_schema_for(name) for name in SUPPORTED_PROVIDERS)
    )
    health = CredentialHealth(vault=Vault(gateway=state.gateway, schemas=schemas))
    report = await health.report(
        auth.scope,
        integrations=SUPPORTED_PROVIDERS,
        # An organisation-scoped token has no team, and a handle needs one. The
        # same fallback the credential routes make, for the same reason: the
        # vault spells the organisation-wide owner as a literal, and a caller
        # with no team of its own is precisely who that owner exists for.
        team_id=auth.team_node_id or CREDENTIAL_ORG_WIDE_TEAM,
    )
    return frozenset(entry.integration for entry in report.entries if entry.state.usable)


def _view(
    onboarding: ProviderOnboarding,
    *,
    configured: bool,
    checked: VerificationRecord | None = None,
) -> ProviderView:
    """Return the listing row for one provider.

    This listing still makes no live call — verifying costs an operator tokens,
    and a page that spent them to render nine rows is a page nobody opens twice.
    What it now reports is what the last check *found*, read from where that
    check was written down. Absent a record it reports that nobody has checked,
    which is a different claim from "it does not work" and is worded as one.
    """
    return ProviderView(
        provider_id=onboarding.provider_id,
        display_name=onboarding.display_name,
        local=onboarding.local,
        configured=configured,
        verified=checked is not None and checked.verified,
        default_model=onboarding.default_model,
        detail=_detail(configured=configured, checked=checked),
    )


def _detail(*, configured: bool, checked: VerificationRecord | None) -> str:
    """Return the sentence under one provider's row.

    Four states rather than two, and each of them is a different next action:
    nothing stored, stored and unchecked, checked and working, checked and
    broken. The one that used to be missing is the last — a deployment whose key
    stopped working read exactly like one nobody had got round to checking.
    """
    if checked is None:
        return _NOT_VERIFIED if configured else _NOT_CONFIGURED
    exercised = f" ({checked.model_id})" if checked.model_id else ""
    if checked.verified:
        return f"a check reached this provider and it answered{exercised}"
    return f"the last check of this provider{exercised} did not pass: {checked.detail}"


@router.get("", response_model=ProviderList)
async def list_providers(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ProviderList:
    """Return every supported provider, in the order the platform documents them."""
    configured = await _configured(state, auth)
    checked = await recorded_checks(
        state.gateway, auth.scope, kind=VerificationSubject.MODEL_PROVIDER
    )
    return ProviderList(
        providers=[
            _view(
                onboarding,
                configured=onboarding.provider_id in configured,
                checked=checked.get(onboarding.provider_id),
            )
            for onboarding in all_onboardings()
        ]
    )


@router.get("/{provider_id}", response_model=ProviderDetailView)
async def show_provider(
    provider_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ProviderDetailView:
    """Return one provider with everything needed to set it up.

    Raises:
        ApiProblem: no supported provider answers to ``provider_id`` (404).
    """
    onboarding = _onboarding(provider_id)
    configured = await _configured(state, auth)
    checked = await recorded_checks(
        state.gateway, auth.scope, kind=VerificationSubject.MODEL_PROVIDER
    )
    listing = _view(
        onboarding, configured=provider_id in configured, checked=checked.get(provider_id)
    )
    return ProviderDetailView(
        **listing.model_dump(),
        fields=[CredentialFieldView(**declared.to_record()) for declared in onboarding.fields],
        guidance=onboarding.guidance,
        where_to_get_it=onboarding.where_to_get_it,
        models=list(onboarding.models),
        install_hint=onboarding.install_hint,
    )


@router.post(
    "/{provider_id}/verify",
    response_model=ProviderVerificationView,
)
async def verify_provider(
    provider_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ProviderVerificationView:
    """Check ``provider_id`` end to end and report what came back.

    A real request, and the claim being made is about what happened rather than
    about what is configured. "It should work now" is not the same statement as
    "a call went out, called a tool, and returned structure", and the difference
    is discovered at 03:00 by whoever was told the first one.

    The model exercised is the one this deployment is configured to run, when
    the configuration names one for this provider. An operator told "choose a
    model that supports tool calling" changes the configuration and presses the
    button again — a check that kept testing the registry's default would
    return the same refusal forever.

    Raises:
        ApiProblem: no supported provider answers to ``provider_id`` (404).
    """
    _onboarding(provider_id)
    configured = await _configured_model(state, auth, provider_id)
    verify = state.model_verifier
    verdict = await (
        verify(provider_id, configured)
        if verify is not None
        else _preflight(provider_id, configured)
    )
    await record_check(
        state.gateway,
        auth.scope,
        kind=VerificationSubject.MODEL_PROVIDER,
        subject=provider_id,
        passed=verdict.satisfied,
        detail=verdict.summary_line if verdict.satisfied else verdict.limitation,
        checked_by=auth.principal_id,
        team_node_id=auth.team_node_id or CREDENTIAL_ORG_WIDE_TEAM,
        model_id=verdict.model_id,
    )
    return ProviderVerificationView(
        provider_id=verdict.provider_id or provider_id,
        verified=verdict.satisfied,
        model_id=verdict.model_id,
        detail=verdict.summary_line if verdict.satisfied else verdict.limitation,
        remedy=verdict.remedy,
        alternatives=list(verdict.alternatives),
    )


async def _configured_model(
    state: GatewayState, auth: AuthenticatedRequest, provider_id: str
) -> str | None:
    """Return the investigator model configured for ``provider_id``, if any.

    Resolved at the root of the caller's tree — the node the first run writes
    at — and only handed over when the configured provider is the one being
    verified: a model name only means something to the provider it was chosen
    for. Any failure to read resolves to ``None``, which is the registry's
    default; a verification that cannot read configuration is still worth
    running.
    """
    try:
        async with state.gateway.begin(auth.scope) as uow:
            root = await uow.config.root()
        service = ConfigService(
            gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails
        )
        effective = await service.resolve(root.node_id)
        models = effective.values.get("models")
        if not isinstance(models, Mapping):
            return None
        investigator = models.get("investigator")
        if not isinstance(investigator, Mapping):
            return None
        if investigator.get("provider") != provider_id:
            return None
        model = investigator.get("model")
        return model if isinstance(model, str) and model != "" else None
    except Exception:  # noqa: BLE001 — configuration is advisory to a live check
        return None


async def _preflight(provider_id: str, model_id: str | None = None) -> ModelVerdict:
    """Return the verdict a default composition produces for ``provider_id``.

    The same end-to-end check ``make preflight`` runs, against however this
    process resolves provider credentials. A deployment that reaches its models
    through the credential proxy supplies its own verifier on ``GatewayState``
    instead, because only the composition root knows which of the two it is.
    """
    return await verify_model(provider_id=provider_id, model_id=model_id)


__all__ = ["router"]

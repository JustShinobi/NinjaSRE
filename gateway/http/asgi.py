"""The ASGI application a container starts, composed from the operator's configuration.

Every other way into this surface takes a ``GatewayState`` somebody built. This
is the one that builds it, from environment variables, so that
``uvicorn gateway.http.asgi:application --factory`` is a complete command and
the image's entrypoint is a real process rather than a placeholder.

Two of the three things a gateway needs are composed here in full: the
persistence gateway over the configured PostgreSQL, and the token service that
resolves a bearer token against it. Runs, replay, configuration, schedules,
memory, capabilities, health, readiness, and webhook ingestion are all wired to
those and work with nothing further.

The third — what actually drives a ReAct loop for a route-triggered
investigation — is named by the operator, in the same shape this repository
already uses for the chaos and end-to-end suites (``INVESTIGATOR=module:factory``
in the Makefile) and for the same reason: composing a runtime means choosing a
provider, a capability catalogue, and a credential proxy, and guessing those
from whatever ambient configuration happened to be present is how a deployment
investigates with a model nobody chose. Unset, the gateway starts and every
route works except starting an investigation, which refuses with a message
naming the setting rather than failing somewhere further in.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from config.constants.deployment import NINJASRE_INVESTIGATOR_ENV
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from core.agent.interaction.models import Interaction
from gateway.http.app import create_app
from gateway.http.services import InvestigationRunner, InvestigationStart
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.local_accounts import LocalAccount, LocalSignIn
from platform.identity.tokens import TokenService
from platform.observability.logging import get_logger
from platform.persistence.postgres.gateway import PostgresPersistence
from platform.startup.errors import ConfigurationInvalid
from platform.startup.profiles import resolve_topology
from platform.startup.validation import validate

_LOGGER = get_logger(__name__)

#: How an investigator factory is written: ``package.module:callable``. The
#: callable takes no arguments and returns something satisfying
#: ``InvestigationRunner``.
FACTORY_SEPARATOR = ":"


class InvestigatorNotConfigured(RuntimeError):
    """No investigation runtime was named, so an investigation cannot be started.

    Raised when a request tries to start one, not at boot. A deployment whose
    console, history, configuration, and health all work is worth having up
    while somebody wires the runtime; refusing to start would take the whole
    surface away over a setting that most routes do not use.
    """

    def __init__(self) -> None:
        super().__init__(
            f"No investigation runtime is configured. Set {NINJASRE_INVESTIGATOR_ENV} to "
            f"'module:factory' — a callable returning the runner this deployment "
            f"investigates with. Composing one means choosing a provider, a capability "
            f"catalogue, and a credential proxy, which is a deployment decision rather "
            f"than something this process should guess."
        )


def load_investigator(reference: str) -> InvestigationRunner:
    """Return the runner ``reference`` names, in ``module:factory`` form.

    Raises ``ConfigurationInvalid`` naming the setting when the reference cannot
    be resolved — an import error at boot is one an operator can fix, and one
    that surfaced as a 500 during an incident is not.
    """
    module_name, separator, factory_name = reference.partition(FACTORY_SEPARATOR)
    if not separator or not module_name or not factory_name:
        raise ConfigurationInvalid(
            f"{NINJASRE_INVESTIGATOR_ENV}: {reference!r} is not 'module:factory'.",
            settings=[NINJASRE_INVESTIGATOR_ENV],
        )
    try:
        module = import_module(module_name)
        factory = getattr(module, factory_name)
    except (ImportError, AttributeError) as error:
        raise ConfigurationInvalid(
            f"{NINJASRE_INVESTIGATOR_ENV}: {reference!r} could not be imported: {error}.",
            settings=[NINJASRE_INVESTIGATOR_ENV],
        ) from error
    runner: InvestigationRunner = factory()
    return runner


class UnconfiguredInvestigator:
    """Refuses every investigation with a message naming the setting to fix.

    A stand-in rather than ``None``, so the routes keep one collaborator and one
    code path. The refusal is an exception with a remedy in it, which is the
    difference between a deployment somebody can finish configuring and one
    that returns a bare 500.
    """

    async def investigate(self, request: InvestigationStart) -> str:
        """Refuse to investigate, naming the setting that would make it possible."""
        raise InvestigatorNotConfigured

    async def cancel(self, run_id: str) -> None:
        """Refuse, naming what is missing. Nothing is running to be cancelled."""
        raise InvestigatorNotConfigured

    async def take_over(self, run_id: str, *, principal: str) -> None:
        """Refuse, naming what is missing. Nothing is running to be taken over."""
        raise InvestigatorNotConfigured

    async def resume(self, run_id: str) -> None:
        """Refuse, naming what is missing. Nothing was taken over to hand back."""
        raise InvestigatorNotConfigured

    async def queue_message(self, run_id: str, text: str) -> None:
        """Refuse, naming what is missing. There is no run to deliver a message on."""
        raise InvestigatorNotConfigured

    async def pending_interactions(self, run_id: str) -> tuple[Interaction, ...]:
        """Return no interactions.

        The one method that answers rather than refusing. A run started by this
        stand-in does not exist, so it has no open questions — and a route
        listing them should render an empty list rather than an error.
        """
        return ()

    async def find_interaction(self, interaction_id: str) -> Interaction | None:
        """Return ``None``: no interaction exists to be found."""
        return None

    async def answer_interaction(
        self,
        interaction_id: str,
        *,
        text: str,
        principal: str,
        selected_option: str = "",
    ) -> Interaction:
        """Refuse to answer, naming what is missing."""
        raise InvestigatorNotConfigured


@dataclass(frozen=True, slots=True)
class Deployment:
    """The gateway's state and the concrete store behind it.

    The store is carried separately because ``GatewayState.gateway`` is the
    *port*, and the boot sequence needs two things the port does not promise:
    a schema migrator and a connection pool to dispose of. A composition root
    is the one place that may know which backend it built, and this is it.
    """

    state: GatewayState
    store: PostgresPersistence


def build_deployment(environ: Mapping[str, str] | None = None) -> Deployment:
    """Return the composition root this deployment's configuration describes.

    Raises ``ConfigurationInvalid`` when validation finds something fatal —
    before a connection is opened, so an unset database URL reports as an unset
    database URL rather than as a connection failure.
    """
    source = dict(environ if environ is not None else os.environ)

    report = validate(source)
    report.raise_if_invalid()

    topology = resolve_topology(source)
    _LOGGER.info("deployment.profile", summary=topology.summary())
    for finding in report.warnings:
        _LOGGER.warning("deployment.configuration", finding=str(finding))

    store = PostgresPersistence.from_url(source[NINJASRE_DATABASE_URL_ENV])

    reference = source.get(NINJASRE_INVESTIGATOR_ENV, "").strip()
    investigator: InvestigationRunner = (
        load_investigator(reference) if reference else UnconfiguredInvestigator()
    )

    tokens = TokenService(gateway=store)

    # Resolved here rather than per request, so a deployment that still carries
    # the shipped passphrase fails to come up instead of failing at the first
    # sign-in — by which time it is already in front of somebody.
    account = LocalAccount.from_environment(source)
    if account is None:
        _LOGGER.info("deployment.local_account_absent")

    return Deployment(
        state=GatewayState(
            gateway=store,
            tokens=tokens,
            investigator=investigator,
            local_sign_in=LocalSignIn(
                gateway=store,
                tokens=tokens,
                account=account,
                recorder=AuditRecorder(gateway=store),
            ),
        ),
        store=store,
    )


def build_state(environ: Mapping[str, str] | None = None) -> GatewayState:
    """Return only the gateway state, for a caller that owns the store's lifecycle."""
    return build_deployment(environ).state


def application() -> Any:
    """Return the ASGI application, for ``uvicorn ...:application --factory``.

    Serving through this skips the boot sequence — no migrations, no key check —
    so it is for an operator who runs those out of band. The container's
    entrypoint is ``python -m gateway.http.serve``, which does both.
    """
    return create_app(build_state())


__all__ = [
    "FACTORY_SEPARATOR",
    "Deployment",
    "InvestigatorNotConfigured",
    "UnconfiguredInvestigator",
    "application",
    "build_deployment",
    "build_state",
    "load_investigator",
]

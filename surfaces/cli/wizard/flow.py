"""The guided first run: from nothing to a configuration that works.

Four steps, in this order, and the order is the whole design. Provider first,
because nothing else can be verified without one. Credentials into the vault
next, because every later step needs them and none of them may see one.
Integrations third, driven by their own schemas. Verification last, and it is
not optional — a wizard that ended with "that should do it" is a wizard whose
failures are discovered during an incident.

The flow never touches a credential itself. It asks the integration wizard to
collect and store one, and what comes back is a status. Nothing here has a
variable a secret could be sitting in, which is the same absence that makes the
vault's surface checkable by reading it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from core.llm.onboarding import (
    ProviderOnboarding,
    UnknownProviderError,
    all_onboardings,
    onboarding_for,
)
from platform.observability.logging import get_logger
from surfaces.cli.client import PlatformClient
from surfaces.cli.errors import ConfigurationError
from surfaces.cli.models import IntegrationStatus, OnboardingOutcome
from surfaces.cli.wizard.integrations import setup_many
from surfaces.cli.wizard.prompts import Prompter

logger = get_logger(__name__)


def _chosen(provider_id: str) -> ProviderOnboarding:
    """Return the named provider's onboarding, in this surface's error vocabulary.

    The descriptors sit below the surfaces and raise a lookup failure of their
    own. Translating it here is what keeps a mistyped provider a
    ``ConfigurationError`` with an exit code an operator's script can branch on,
    rather than a traceback from a package they have never heard of.

    Raises:
        ConfigurationError: no provider answers to that identifier.
    """
    try:
        return onboarding_for(provider_id)
    except UnknownProviderError as unknown:
        raise ConfigurationError(
            f"{provider_id!r} is not a provider this build knows how to set up",
            remedy=f"choose one of: {', '.join(unknown.known)}",
        ) from unknown


@dataclass(slots=True)
class OnboardingFlow:
    """The guided sequence, as a value so a test can run it end to end."""

    client: PlatformClient
    prompter: Prompter
    #: Chosen ahead of the flow by a caller that already knows — the REPL's
    #: first-run path, an unattended install. Empty means ask.
    provider_id: str = ""
    integrations: tuple[str, ...] = ()
    steps: list[str] = field(default_factory=list)

    def _step(self, message: str) -> None:
        """Record and show one step, so the transcript is the record."""
        self.steps.append(message)
        self.prompter.say(message)

    async def choose_provider(self) -> ProviderOnboarding:
        """Return the provider the operator picked, having shown them the nine.

        All nine are offered with the same weight, local included. A list that
        buried the local option under a heading would make provider neutrality
        true in the adapter layer and false where somebody actually decides.
        """
        available = all_onboardings()
        if not available:
            raise ConfigurationError("this build declares no providers")

        if self.provider_id:
            return _chosen(self.provider_id)

        self.prompter.say("Which model provider should this deployment use?")
        for onboarding in available:
            marker = "runs locally" if onboarding.local else "hosted"
            self.prompter.say(f"  {onboarding.provider_id} — {onboarding.display_name} ({marker})")

        chosen = self.prompter.choose(
            "Provider",
            [onboarding.provider_id for onboarding in available],
            default=available[0].provider_id,
        )
        return _chosen(chosen)

    async def enter_provider_credential(self, onboarding: ProviderOnboarding) -> IntegrationStatus:
        """Collect the provider's credential into the vault and report on it.

        Through the same path an integration takes. A provider key that went
        somewhere else would be a second place credentials live, and the second
        place is the one the audit misses.
        """
        if onboarding.guidance:
            self.prompter.say(onboarding.guidance)
        if onboarding.where_to_get_it:
            self.prompter.say(f"Where to get it: {onboarding.where_to_get_it}")

        outcomes = await setup_many(self.client, (onboarding.provider_id,), self.prompter)
        return outcomes[0].status

    async def choose_model(self, onboarding: ProviderOnboarding) -> str:
        """Return the model to use, offering the ones this provider is known for."""
        if not onboarding.models:
            return self.prompter.ask("Model", default=onboarding.default_model)
        return self.prompter.choose(
            "Model", list(onboarding.models), default=onboarding.default_model
        )

    async def choose_integrations(self) -> tuple[str, ...]:
        """Return the integrations to set up.

        Offered rather than required. A deployment with a provider and no
        integrations still investigates — from what it is told rather than from
        what it can look up — and forcing a choice here is how somebody
        abandons the flow at step three.
        """
        if self.integrations:
            return self.integrations

        known = await self.client.list_integrations()
        if not known:
            return ()

        self.prompter.say("Which integrations should this deployment use?")
        # What the estate turned up comes first and carries its address, because
        # the hard part of this step is not choosing a vendor — it is knowing
        # which of fifty-seven containers is the one. The deployment already
        # swept the cluster and the answer is in the catalogue's own order.
        found = [status for status in known if status.suggested_address]
        if found:
            self.prompter.say(
                "  found in your estate: "
                + ", ".join(
                    f"{status.integration} ({status.suggested_address})" for status in found
                )
            )
        self.prompter.say(f"  available: {', '.join(status.integration for status in known)}")
        answer = self.prompter.ask(
            "Integrations, comma-separated (empty to skip)",
            help_text="You can add more later with 'ninjasre integrations setup'.",
        )
        return tuple(name.strip() for name in answer.split(",") if name.strip())

    async def verify(self, onboarding: ProviderOnboarding) -> tuple[bool, str]:
        """Check the provider end to end and return whether it worked.

        Not optional. "It should work now" is not the same claim as "a request
        went out and came back", and the difference is discovered at 03:00.
        """
        status = await self.client.verify_provider(onboarding.provider_id)
        return status.verified, status.detail

    async def run(self) -> OnboardingOutcome:
        """Run the whole flow and return what it left behind."""
        onboarding = await self.choose_provider()
        self._step(f"provider: {onboarding.provider_id}")

        credential = await self.enter_provider_credential(onboarding)
        self._step(
            f"credential stored in the vault for {onboarding.provider_id}"
            if credential.configured
            else f"credential for {onboarding.provider_id} was not stored"
        )

        model = await self.choose_model(onboarding)
        self._step(f"model: {model}")

        chosen = await self.choose_integrations()
        integration_outcomes = await setup_many(self.client, chosen, self.prompter)
        for outcome in integration_outcomes:
            self._step(
                f"integration {outcome.status.integration}: "
                f"{'verified' if outcome.usable else 'not usable'}"
            )

        verified, detail = await self.verify(onboarding)
        self._step("verified" if verified else f"verification failed: {detail}")

        logger.info(
            "cli.onboarding_finished",
            provider=onboarding.provider_id,
            model=model,
            integrations=[outcome.status.integration for outcome in integration_outcomes],
            verified=verified,
        )
        return OnboardingOutcome(
            provider_id=onboarding.provider_id,
            model_id=model,
            integrations=tuple(outcome.status for outcome in integration_outcomes),
            verified=verified,
            steps=tuple(self.steps),
            detail=detail,
        )


async def onboard(
    client: PlatformClient,
    prompter: Prompter,
    *,
    provider_id: str = "",
    integrations: Sequence[str] = (),
) -> OnboardingOutcome:
    """Run the guided first-run flow and return what it produced."""
    flow = OnboardingFlow(
        client=client,
        prompter=prompter,
        provider_id=provider_id,
        integrations=tuple(integrations),
    )
    return await flow.run()


__all__ = ["OnboardingFlow", "onboard"]

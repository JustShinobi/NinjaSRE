"""Setting one integration up, from its own schema rather than from a list here.

The prompts are generated from the credential schema the integration package
declares, so adding a vendor is a package and not an edit to this file. That is
the property that makes a catalogue of eighty-five integrations addable one at
a time, and it is the same reason capability discovery walks the tree.

The credential goes from the prompt to the vault and nowhere else. It is never
a command argument, never written to configuration, never logged, and never
returned by anything here — ``setup`` hands back a status, and a status has no
field a secret could sit in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from platform.credentials.fields import CredentialFieldSpec
from platform.observability.logging import get_logger
from surfaces.cli.client import PlatformClient
from surfaces.cli.errors import ConfigurationError
from surfaces.cli.models import IntegrationStatus
from surfaces.cli.wizard.prompts import Prompter

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SetupOutcome:
    """What setting one integration up produced.

    ``entered`` names the fields that were filled, never their values. Enough
    for an operator to see that the optional one they skipped is the reason
    verification failed, and nothing a secret could ride out on.
    """

    status: IntegrationStatus
    entered: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Return whether the integration verified after being set up."""
        return self.status.healthy


def collect(fields: Sequence[CredentialFieldSpec], prompter: Prompter) -> dict[str, str]:
    """Return the values a person entered for ``fields``.

    Secret fields are read without echo. Optional ones may be left empty and
    are then absent rather than present-and-empty, because a schema that
    distinguishes "not set" from "set to nothing" would otherwise stop being
    able to.

    Raises:
        ConfigurationError: a required field was left empty.
    """
    values: dict[str, str] = {}
    for spec in fields:
        answer = (
            prompter.secret(spec.prompt, help_text=spec.help)
            if spec.secret
            else prompter.ask(spec.prompt, help_text=spec.help)
        ).strip()

        if not answer:
            if spec.required:
                raise ConfigurationError(
                    f"{spec.prompt} is required",
                    remedy="run the setup again and provide it",
                )
            continue
        values[spec.name] = answer
    return values


async def setup(
    client: PlatformClient,
    integration: str,
    prompter: Prompter,
    *,
    verify: bool = True,
) -> SetupOutcome:
    """Prompt for ``integration``'s credential, store it, and check it works.

    Raises:
        ConfigurationError: the integration declares no fields, or a required
            one was left empty.
    """
    fields = await client.credential_fields(integration)
    if not fields:
        raise ConfigurationError(
            f"{integration!r} declares no credential fields",
            remedy="check that the integration package is installed",
        )

    prompter.say(f"Setting up {integration}.")
    values = collect(fields, prompter)

    stored = await client.store_integration_credential(integration, values)
    logger.info(
        "cli.integration_credential_stored",
        integration=integration,
        # The field *names*, never their values. This log line is the one that
        # would be pasted into a support thread.
        fields=sorted(values),
    )

    status = await client.verify_integration(integration) if verify else stored
    entered = tuple(sorted(values))
    skipped = tuple(sorted(spec.name for spec in fields if spec.name not in values))
    return SetupOutcome(status=status, entered=entered, skipped=skipped)


async def setup_many(
    client: PlatformClient,
    integrations: Sequence[str],
    prompter: Prompter,
) -> tuple[SetupOutcome, ...]:
    """Set several integrations up in order, continuing past one that fails.

    Continuing, because an operator who mistyped a Datadog key should still
    finish configuring Kubernetes rather than starting the whole flow again.
    What failed is reported at the end.
    """
    outcomes: list[SetupOutcome] = []
    for integration in integrations:
        try:
            outcomes.append(await setup(client, integration, prompter))
        except ConfigurationError as failed:
            prompter.say(f"{integration}: {failed}")
            outcomes.append(
                SetupOutcome(
                    status=IntegrationStatus(
                        integration=integration, configured=False, detail=str(failed)
                    )
                )
            )
    return tuple(outcomes)


def summarise(outcomes: Sequence[SetupOutcome]) -> Mapping[str, bool]:
    """Return which integrations came out usable, by name."""
    return {outcome.status.integration: outcome.usable for outcome in outcomes}


__all__ = [
    "SetupOutcome",
    "collect",
    "setup",
    "setup_many",
    "summarise",
]

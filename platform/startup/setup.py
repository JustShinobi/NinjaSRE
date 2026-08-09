"""The first fifteen minutes, as a plan with a budget on each step.

SC-001 is a wall-clock claim — a fresh operator reaches their first successful
investigation in under fifteen minutes — and a wall-clock claim needs two
different things to stay true. Somebody has to measure it on a clean machine,
which ``tools/measure_first_investigation.py`` does for the legs that are
deterministic. And the *shape* of the path has to stay short, which is what this
module holds: every step a fresh operator takes, with the time it is allowed,
and a total that is checked against the budget.

The value of writing it down is that a step added later has to be given a
budget, and giving it one is where somebody notices the total no longer fits.
That is a cheaper place to find out than a demo.

The budgets are deliberate rather than measured, with one exception. Pulling
images depends on a network nobody here controls, so its budget is the largest
and is the first thing to look at when a real run misses. Everything else is
something this repository can hold itself to.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Final

from config.constants.deployment import (
    FIRST_INVESTIGATION_BUDGET_SECONDS,
    NINJASRE_ADMIN_TOKEN_ENV,
)
from platform.startup.keys import KEY_GENERATOR_HINT
from platform.startup.profiles import DeploymentProfile, topology_for

#: Bytes of entropy in a generated first-run admin token. 32 bytes, URL-safe,
#: which is the same shape the identity layer issues and long enough that a
#: token printed to a terminal is not worth guessing at.
ADMIN_TOKEN_BYTES: Final[int] = 32


@dataclass(frozen=True, slots=True)
class SetupStep:
    """One thing a fresh operator does, and how long it is allowed to take."""

    name: str
    action: str
    budget_seconds: int
    automated: bool = False

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the console's setup view reads."""
        return {
            "name": self.name,
            "action": self.action,
            "budget_seconds": self.budget_seconds,
            "automated": self.automated,
        }

    def __str__(self) -> str:
        who = "automatic" if self.automated else "you"
        return f"{self.name} ({self.budget_seconds}s, {who}): {self.action}"


@dataclass(frozen=True, slots=True)
class SetupPlan:
    """Every step from a clean machine to a finished investigation."""

    profile: DeploymentProfile
    steps: tuple[SetupStep, ...]
    budget_seconds: int = FIRST_INVESTIGATION_BUDGET_SECONDS

    @property
    def total_seconds(self) -> int:
        """Return the sum of every step's budget."""
        return sum(step.budget_seconds for step in self.steps)

    @property
    def manual_seconds(self) -> int:
        """Return the part of the budget an operator spends typing or thinking."""
        return sum(step.budget_seconds for step in self.steps if not step.automated)

    @property
    def within_budget(self) -> bool:
        """Return whether this path fits the fifteen minutes SC-001 allows."""
        return self.total_seconds <= self.budget_seconds

    @property
    def headroom_seconds(self) -> int:
        """Return what is left of the budget after every step's allowance."""
        return self.budget_seconds - self.total_seconds

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a setup view or a report reads."""
        return {
            "profile": str(self.profile),
            "steps": [step.to_record() for step in self.steps],
            "total_seconds": self.total_seconds,
            "budget_seconds": self.budget_seconds,
            "within_budget": self.within_budget,
        }

    def summary(self) -> str:
        """Return the numbered list a quickstart document shows."""
        lines = [f"First investigation on the {self.profile} profile, in {len(self.steps)} steps:"]
        lines.extend(f"  {index}. {step}" for index, step in enumerate(self.steps, start=1))
        lines.append(
            f"  budget {self.budget_seconds}s, planned {self.total_seconds}s, "
            f"headroom {self.headroom_seconds}s"
        )
        return "\n".join(lines)


#: The standard profile's path. Four containers, one credential, one command.
_STANDARD_STEPS: tuple[SetupStep, ...] = (
    SetupStep(
        name="clone",
        action="clone the repository and change into deploy/compose",
        budget_seconds=30,
    ),
    SetupStep(
        name="configure",
        action=(
            "copy .env.example to .env, paste one provider API key, and generate an "
            f"encryption key with {KEY_GENERATOR_HINT}"
        ),
        budget_seconds=120,
    ),
    SetupStep(
        name="pull",
        action="docker compose pull — the only step whose length depends on your network",
        budget_seconds=300,
        automated=True,
    ),
    SetupStep(
        name="start",
        action="docker compose up -d: four containers, health-gated in dependency order",
        budget_seconds=90,
        automated=True,
    ),
    SetupStep(
        name="migrate",
        action="migrations apply at startup under an advisory lock; nothing to run",
        budget_seconds=30,
        automated=True,
    ),
    SetupStep(
        name="sign in",
        action="open the console and paste the admin token the logs printed once",
        budget_seconds=60,
    ),
    SetupStep(
        name="investigate",
        action="send the sample alert and read the evidence-backed answer that comes back",
        budget_seconds=180,
    ),
)

#: The dev profile skips the image pull — a contributor builds from the checkout
#: — and pays for the build instead, which is why the total is close rather than
#: obviously smaller.
_DEV_STEPS: tuple[SetupStep, ...] = (
    SetupStep(
        name="clone",
        action="clone the repository and run make install",
        budget_seconds=180,
    ),
    SetupStep(
        name="configure",
        action="copy .env.example to .env and paste one provider API key",
        budget_seconds=90,
    ),
    SetupStep(
        name="start",
        action="docker compose -f docker-compose.dev.yml up -d: PostgreSQL and the application",
        budget_seconds=120,
        automated=True,
    ),
    SetupStep(
        name="migrate",
        action="migrations apply at startup; the credential proxy runs in-process",
        budget_seconds=30,
        automated=True,
    ),
    SetupStep(
        name="investigate",
        action="ninjasre investigate against a synthetic scenario, with no cluster in sight",
        budget_seconds=180,
    ),
)

#: The enterprise path is a Helm install, and its extra steps are the ones a
#: regulated environment has anyway: a values file and a secret.
_ENTERPRISE_STEPS: tuple[SetupStep, ...] = (
    SetupStep(
        name="values",
        action="copy values.yaml, set the database and the provider secret reference",
        budget_seconds=240,
    ),
    SetupStep(
        name="secrets",
        action="create the encryption-key and provider-credential secrets in the namespace",
        budget_seconds=120,
    ),
    SetupStep(
        name="install",
        action="helm install: the migration job runs to completion before the rollout",
        budget_seconds=240,
        automated=True,
    ),
    SetupStep(
        name="sign in",
        action="sign in through your identity provider",
        budget_seconds=90,
    ),
    SetupStep(
        name="investigate",
        action="send the sample alert and read the answer",
        budget_seconds=180,
    ),
)

#: The homelab path has two steps the others do not, and both are there because
#: of what this profile assumes.
#:
#: **The model is probed rather than trusted.** A homelab runs the model on the
#: operator's own hardware, and a quantised build that accepts a fraction of its
#: advertised window — or emits prose where a tool call belongs — fails in the
#: middle of the first incident rather than at setup. The probe costs about
#: twenty small local calls and is cached against the model's identity, so it is
#: paid once.
#:
#: **The cluster token is pasted before the first investigation.** The point of
#: this profile is watching infrastructure the operator already has, so a first
#: run that ended at a synthetic scenario would have demonstrated nothing they
#: came for.
_HOMELAB_STEPS: tuple[SetupStep, ...] = (
    SetupStep(
        name="configure",
        action="copy .env.example to .env and set an encryption key and a model endpoint",
        budget_seconds=120,
    ),
    SetupStep(
        name="start",
        action=(
            "docker compose -f docker-compose.homelab.yml up -d: four containers inside a "
            "declared memory and CPU footprint"
        ),
        budget_seconds=180,
        automated=True,
    ),
    SetupStep(
        name="probe the model",
        action=(
            "probe the local endpoint for tool calling, structured output, streaming and its "
            "real usable context, and report what it cannot do before anything depends on it"
        ),
        budget_seconds=180,
        automated=True,
    ),
    SetupStep(
        name="connect",
        action="paste a Proxmox API token; the estate populates and the guardian offers itself",
        budget_seconds=120,
    ),
    SetupStep(
        name="investigate",
        action="read what the shipped detectors already conclude about the cluster",
        budget_seconds=180,
    ),
)

_PLANS: dict[DeploymentProfile, tuple[SetupStep, ...]] = {
    DeploymentProfile.DEV: _DEV_STEPS,
    DeploymentProfile.HOMELAB: _HOMELAB_STEPS,
    DeploymentProfile.STANDARD: _STANDARD_STEPS,
    DeploymentProfile.ENTERPRISE: _ENTERPRISE_STEPS,
}


def first_run_plan(profile: DeploymentProfile = DeploymentProfile.STANDARD) -> SetupPlan:
    """Return the path from a clean machine to a first investigation on ``profile``."""
    return SetupPlan(profile=profile, steps=_PLANS[profile])


def generate_admin_token() -> str:
    """Return a fresh first-run administrator token.

    Generated rather than defaulted. A shipped default admin token is a
    deployment everybody has the credentials to, and this is the one secret
    where generating beats requiring — unlike the encryption key, a token that
    is lost costs a restart rather than every stored credential.
    """
    return secrets.token_urlsafe(ADMIN_TOKEN_BYTES)


def admin_token_announcement(token: str, *, profile: DeploymentProfile) -> str:
    """Return the block printed once at first start, with the token in it.

    Printed rather than logged at a level something might filter, and printed
    once: an operator who loses it restarts with ``NINJASRE_ADMIN_TOKEN`` set to
    one they chose, which is the path this message names.
    """
    topology = topology_for(profile)
    rule = "=" * 72
    return "\n".join(
        [
            rule,
            "  NinjaSRE first start — this is the only time this token is shown.",
            "",
            f"    admin token: {token}",
            "",
            "  Sign in to the console with it, then create your own account.",
            f"  Set {NINJASRE_ADMIN_TOKEN_ENV} before starting if you would rather",
            "  choose the token yourself.",
            "",
            f"  {topology.summary()}",
            rule,
        ]
    )


__all__ = [
    "ADMIN_TOKEN_BYTES",
    "SetupPlan",
    "SetupStep",
    "admin_token_announcement",
    "first_run_plan",
    "generate_admin_token",
]

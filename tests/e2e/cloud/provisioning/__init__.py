"""Bringing infrastructure up, tagging everything, and taking it down again.

Declarative rather than a sequence of API calls, because the property that
matters is that *destroy* knows what *apply* created. A script that creates six
things and a script that deletes six things are two lists that drift; a
declarative module and its state are one.

Tagging is not book-keeping here, it is the recovery mechanism. Every resource
carries the suite, the run, the scenario, and when it was made, so a run that
was killed leaves resources that a sweep can find, attribute, and destroy
without knowing anything about the run that made them.

The provisioning tool is reached through the command port, which has two
consequences worth stating. The whole lifecycle is assertable with no cloud
account — the assertions are about which commands were issued, which is what a
teardown bug actually is. And no credential passes through this process: the
tool authenticates itself from the operator's own environment, and there is
nothing here for a secret to be held in.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from config.constants.chaos import (
    CLOUD_CREATED_TAG_KEY,
    CLOUD_PROVISION_TIMEOUT_SECONDS,
    CLOUD_RUN_TAG_KEY,
    CLOUD_SCENARIO_TAG_KEY,
    CLOUD_SUITE_TAG_KEY,
    CLOUD_SUITE_TAG_VALUE,
)
from tests.support.commands import CommandRunner
from tests.support.interruption import on_interrupt

#: The declarative tool the modules are written for.
PROVISIONER = "terraform"

#: Where the declarative modules live.
MODULES_ROOT: Path = Path(__file__).resolve().parent / "modules"


class ProvisioningError(RuntimeError):
    """Infrastructure could not be brought up, or could not be taken down."""


@dataclass(frozen=True, slots=True)
class Resource:
    """One provisioned thing, as the reaper needs to see it."""

    kind: str
    identifier: str
    tags: Mapping[str, str] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        """Return the run this resource was provisioned for, if it says."""
        return self.tags.get(CLOUD_RUN_TAG_KEY, "")

    @property
    def scenario_id(self) -> str:
        """Return the scenario this resource belongs to, if it says."""
        return self.tags.get(CLOUD_SCENARIO_TAG_KEY, "")

    @property
    def created_at(self) -> str:
        """Return when this suite made it, in ISO 8601, if it says."""
        return self.tags.get(CLOUD_CREATED_TAG_KEY, "")

    @property
    def attributable(self) -> bool:
        """Return whether this resource carries enough to be reaped safely.

        A resource with the suite tag and no run tag is one the sweep can see
        and must not destroy: it cannot tell a live run's resource from a dead
        one's, and guessing in an account that holds something else is how a
        reaper becomes the outage.
        """
        return bool(self.run_id and self.created_at)

    def age_seconds(self, *, now: datetime | None = None) -> float:
        """Return how long ago this suite made it, or ``inf`` if it does not say."""
        moment = now if now is not None else datetime.now(UTC)
        try:
            made = datetime.fromisoformat(self.created_at)
        except ValueError:
            return float("inf")
        return (moment - made).total_seconds()


def tags_for(*, run_id: str, scenario_id: str, at: datetime | None = None) -> dict[str, str]:
    """Return the tags every resource this suite provisions must carry."""
    moment = at if at is not None else datetime.now(UTC)
    return {
        CLOUD_SUITE_TAG_KEY: CLOUD_SUITE_TAG_VALUE,
        CLOUD_RUN_TAG_KEY: run_id,
        CLOUD_SCENARIO_TAG_KEY: scenario_id,
        CLOUD_CREATED_TAG_KEY: moment.isoformat(timespec="seconds"),
    }


@dataclass(frozen=True, slots=True)
class StackPlan:
    """One scenario's infrastructure, named and tagged for one run."""

    scenario_id: str
    run_id: str
    module: str
    variables: Mapping[str, str] = field(default_factory=dict)
    region: str = "eu-west-1"
    at: datetime | None = None

    @property
    def workspace(self) -> str:
        """Return the isolated state this run's infrastructure lives in.

        Per run rather than per scenario: two runs of the same scenario against
        one account must not share state, or the second one's destroy takes down
        the first one's resources.
        """
        return f"{self.scenario_id}-{self.run_id}"

    def tags(self) -> dict[str, str]:
        """Return the tags this plan's resources carry."""
        return tags_for(run_id=self.run_id, scenario_id=self.scenario_id, at=self.at)

    def variable_arguments(self) -> tuple[str, ...]:
        """Return the declarative variables, tags included, as command arguments."""
        declared = {
            **self.variables,
            "region": self.region,
            "run_id": self.run_id,
            "tags": json.dumps(self.tags(), sort_keys=True),
        }
        arguments: list[str] = []
        for name, value in sorted(declared.items()):
            arguments += ["-var", f"{name}={value}"]
        return tuple(arguments)


@runtime_checkable
class Provisioner(Protocol):
    """Whatever brings a stack up, takes it down, and can list what is out there."""

    def apply(self, plan: StackPlan) -> tuple[Resource, ...]:
        """Bring ``plan``'s infrastructure up and return what it created."""

    def destroy(self, plan: StackPlan) -> tuple[str, ...]:
        """Take ``plan``'s infrastructure down and return what went."""

    def inventory(self) -> tuple[Resource, ...]:
        """Return every resource in the account carrying this suite's tag."""

    def destroy_by_run(self, run_id: str) -> tuple[str, ...]:
        """Destroy everything tagged for ``run_id``, whoever provisioned it."""


@dataclass(frozen=True, slots=True)
class DeclarativeProvisioner:
    """Drives the declarative tool, in a per-run workspace, over the command port."""

    runner: CommandRunner
    root: Path = MODULES_ROOT
    binary: str = PROVISIONER
    timeout_seconds: float = CLOUD_PROVISION_TIMEOUT_SECONDS

    def _argv(self, plan: StackPlan, *arguments: str) -> tuple[str, ...]:
        return (self.binary, f"-chdir={self.root / plan.module}", *arguments)

    def _run(self, plan: StackPlan, *arguments: str) -> str:
        result = self.runner.run(self._argv(plan, *arguments), timeout=self.timeout_seconds)
        if not result.ok:
            raise ProvisioningError(f"{' '.join(arguments)}: {result.message}")
        return result.stdout

    def apply(self, plan: StackPlan) -> tuple[Resource, ...]:
        """Bring ``plan``'s infrastructure up and return what it created.

        Raises:
            ProvisioningError: the tool refused; ``destroy`` still applies,
                because a partial apply has created real resources.
        """
        self._run(plan, "init", "-input=false")
        self._run(plan, "workspace", "select", "-or-create", plan.workspace)
        self._run(plan, "apply", "-input=false", "-auto-approve", *plan.variable_arguments())
        return self.outputs(plan)

    def outputs(self, plan: StackPlan) -> tuple[Resource, ...]:
        """Return the resources the module says it created."""
        document = self._run(plan, "output", "-json")
        try:
            parsed = json.loads(document or "{}")
        except json.JSONDecodeError:
            return ()
        declared = parsed.get("resources", {})
        values = declared.get("value") if isinstance(declared, Mapping) else declared
        return tuple(_resource(item) for item in values or () if isinstance(item, Mapping))

    def destroy(self, plan: StackPlan) -> tuple[str, ...]:
        """Take ``plan``'s infrastructure down and return what went."""
        existing = {resource.identifier for resource in self._safe_outputs(plan)}
        self._run(plan, "workspace", "select", "-or-create", plan.workspace)
        self._run(plan, "destroy", "-input=false", "-auto-approve", *plan.variable_arguments())
        return tuple(sorted(existing))

    def _safe_outputs(self, plan: StackPlan) -> tuple[Resource, ...]:
        """Return the outputs, or nothing when the state cannot be read."""
        try:
            return self.outputs(plan)
        except ProvisioningError:
            return ()

    def inventory(self) -> tuple[Resource, ...]:
        """Return every resource in the account carrying this suite's tag."""
        result = self.runner.run(
            (
                "aws",
                "resourcegroupstaggingapi",
                "get-resources",
                "--tag-filters",
                f"Key={CLOUD_SUITE_TAG_KEY},Values={CLOUD_SUITE_TAG_VALUE}",
                "--output",
                "json",
            ),
            timeout=self.timeout_seconds,
        )
        if not result.ok:
            raise ProvisioningError(f"the account could not be listed: {result.message}")
        try:
            document = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as failure:
            raise ProvisioningError(f"the account listing was not JSON: {failure}") from failure
        return tuple(
            _tagged_resource(item)
            for item in document.get("ResourceTagMappingList") or ()
            if isinstance(item, Mapping)
        )

    def destroy_by_run(self, run_id: str) -> tuple[str, ...]:
        """Destroy everything tagged for ``run_id``, whoever provisioned it.

        Goes through the same declarative workspaces the runs used, because
        deleting cloud resources one API call at a time is how a reaper leaves
        half a VPC behind.
        """
        destroyed: list[str] = []
        for resource in self.inventory():
            if resource.run_id != run_id or not resource.scenario_id:
                continue
            plan = StackPlan(
                scenario_id=resource.scenario_id, run_id=run_id, module=resource.scenario_id
            )
            destroyed.extend(self.destroy(plan))
        return tuple(sorted(set(destroyed)))


@dataclass(slots=True)
class Teardown:
    """The plan being torn down, and what the teardown actually destroyed.

    Mutable and yielded, because what went is only known after the block ends —
    and a run that reported nothing destroyed would be indistinguishable from one
    whose teardown never ran.
    """

    plan: StackPlan
    destroyed: list[str] = field(default_factory=list)
    failed: bool = False


@contextmanager
def deferred_teardown(provisioner: Provisioner, plan: StackPlan) -> Iterator[Teardown]:
    """Yield a record and destroy ``plan``'s infrastructure on every way out.

    Including the signalled way. A cloud stack that outlives its run is a bill
    that keeps arriving, which is a materially worse failure than a chaos fault
    somebody notices in an hour.

    Raises:
        RunInterrupted: a signal arrived; the stack was destroyed first.
    """
    record = Teardown(plan=plan)

    def take_it_down() -> None:
        # A destroy that raised here would replace one stack this could not
        # remove with every stack after it going unremoved too. The reaper is
        # the second line for exactly this case.
        try:
            record.destroyed.extend(provisioner.destroy(plan))
        except ProvisioningError:
            record.failed = True

    try:
        with on_interrupt(take_it_down, what=f"the {plan.scenario_id} cloud run"):
            yield record
    finally:
        take_it_down()


def _resource(item: Mapping[str, Any]) -> Resource:
    """Return one resource the declarative module reported."""
    return Resource(
        kind=str(item.get("kind", "")),
        identifier=str(item.get("id", item.get("arn", ""))),
        tags={str(key): str(value) for key, value in (item.get("tags") or {}).items()},
    )


def _tagged_resource(item: Mapping[str, Any]) -> Resource:
    """Return one resource the account's tag index reported."""
    arn = str(item.get("ResourceARN", ""))
    tags = {
        str(entry.get("Key", "")): str(entry.get("Value", ""))
        for entry in item.get("Tags") or ()
        if isinstance(entry, Mapping)
    }
    return Resource(kind=_kind_of(arn), identifier=arn, tags=tags)


def _kind_of(arn: str) -> str:
    """Return the service an ARN belongs to, which is all the reaper reports."""
    parts: Sequence[str] = arn.split(":")
    return parts[2] if len(parts) > 2 else ""


__all__ = [
    "MODULES_ROOT",
    "PROVISIONER",
    "DeclarativeProvisioner",
    "Provisioner",
    "ProvisioningError",
    "Resource",
    "StackPlan",
    "Teardown",
    "deferred_teardown",
    "tags_for",
]

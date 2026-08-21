"""What is wrong with this deployment, all of it, in one pass, with what to do.

Three decisions, and the first is the one that makes the rest worth having.

**A finding carries an action or it does not exist.** ``Finding`` refuses to be
constructed without both a problem and a next action, so the string
"connection error" cannot reach an operator from here. This is a type doing the
work a code review would otherwise have to do every time somebody adds a check,
and it is the difference between a diagnostic that helps and one that restates
the exception it caught.

**Every check runs, every time.** They are independent, they run concurrently,
and one that fails does not stop the others. An operator with three problems
should learn all three from one run — the alternative is one restart per
problem, which is how a ten-minute setup becomes an hour.

**A check that does not answer is a finding, not a hang.** Every check has its
own timeout. The dependencies most worth checking are the ones most likely to be
unreachable, and "unreachable" and "slow" look identical from here, so the check
gives each one a bounded moment and reports the ones that did not use it.

The report is ordered by how much each finding blocks. That ordering is the
report's only editorial content and it is what stops a self-check becoming a
wall of ticks nobody reads: what stops the deployment working comes first, and a
pass says so briefly rather than exhaustively.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from config.constants.first_run import (
    BLOCKING_ORDER,
    BLOCKS_EVERYTHING,
    BLOCKS_INVESTIGATION,
    BLOCKS_ONE_FEATURE,
    CHECK_CLOCK_SKEW,
    CHECK_CREDENTIAL_PROXY,
    CHECK_DATABASE,
    CHECK_DISK_SPACE,
    CHECK_INTEGRATIONS,
    CHECK_INVESTIGATION_RUNTIME,
    CHECK_MODEL_PROVIDER,
    CHECK_OBSERVER,
    CHECK_SCHEDULER,
    CHECK_SCHEMA,
    DEGRADES,
    MAXIMUM_CLOCK_SKEW_SECONDS,
    MINIMUM_FREE_DISK_BYTES,
    SELF_CHECK_TIMEOUT_SECONDS,
)
from platform.persistence.ports.health import StoreHealth
from platform.persistence.ports.transaction import PersistenceGateway

#: How a size is reported to a person. Bytes are exact and unreadable; an
#: operator deciding whether to add a disk is thinking in gibibytes.
_UNITS: tuple[tuple[str, int], ...] = (
    ("GiB", 1024**3),
    ("MiB", 1024**2),
    ("KiB", 1024),
)


def human_bytes(count: int) -> str:
    """Return ``count`` in the largest unit that leaves a number worth reading."""
    for suffix, size in _UNITS:
        if count >= size:
            return f"{count / size:.1f} {suffix}"
    return f"{count} bytes"


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing that is wrong, what to do about it, and how much it takes away.

    Both strings are required and both are validated non-empty. FR-009 is not a
    convention here: a finding without an action cannot be built, so no surface
    can be handed one.
    """

    check: str
    problem: str
    action: str
    blocks: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.problem.strip() or not self.action.strip():
            raise ValueError(
                f"a finding from {self.check!r} needs both a problem and a next action. "
                f"'Something failed' is a restatement of the exception, not a diagnosis."
            )
        if self.blocks not in BLOCKING_ORDER:
            raise ValueError(
                f"{self.blocks!r} is not one of {', '.join(BLOCKING_ORDER)}. A finding has "
                f"to say how much it blocks or the report cannot be ordered."
            )

    @property
    def weight(self) -> int:
        """Return this finding's place in the blocking order. Lower blocks more."""
        return BLOCKING_ORDER.index(self.blocks)

    @property
    def is_blocking(self) -> bool:
        """Return whether this stops the deployment doing something it is for."""
        return self.blocks != DEGRADES

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console and the CLI both read."""
        return {
            "check": self.check,
            "problem": self.problem,
            "action": self.action,
            "blocks": self.blocks,
            "detail": dict(self.detail),
        }

    def __str__(self) -> str:
        return f"[{self.blocks}] {self.check}: {self.problem} → {self.action}"


@dataclass(frozen=True, slots=True)
class Passed:
    """A check that found nothing. Reported briefly, on purpose."""

    check: str
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form."""
        return {"check": self.check, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one check came back with: nothing, or one or more findings."""

    check: str
    findings: tuple[Finding, ...] = ()
    detail: str = ""

    @classmethod
    def fine(cls, check: str, *, detail: str = "") -> CheckOutcome:
        """Return the outcome of a check that found nothing."""
        return cls(check=check, detail=detail)

    @classmethod
    def problem(
        cls,
        check: str,
        *,
        problem: str,
        action: str,
        blocks: str,
        detail: Mapping[str, Any] | None = None,
    ) -> CheckOutcome:
        """Return the outcome of a check that found one thing wrong."""
        return cls(
            check=check,
            findings=(
                Finding(
                    check=check,
                    problem=problem,
                    action=action,
                    blocks=blocks,
                    detail=dict(detail or {}),
                ),
            ),
        )

    @classmethod
    def problems(cls, check: str, findings: Iterable[Finding]) -> CheckOutcome:
        """Return the outcome of a check that found several."""
        return cls(check=check, findings=tuple(findings))


class CheckBody(Protocol):
    """What a check is: something awaitable that returns an outcome, taking nothing.

    Taking nothing is deliberate. Everything a check needs is bound when it is
    built, which is what lets the whole set be assembled by a composition root
    and driven by a unit test with no deployment behind it.
    """

    async def __call__(self) -> CheckOutcome:
        """Return what this check found, or nothing."""


@dataclass(frozen=True, slots=True)
class Check:
    """One named check and the bounded moment it is allowed."""

    name: str
    run: CheckBody


@dataclass(frozen=True, slots=True)
class SelfCheckReport:
    """Every problem this deployment has, and everything that is fine."""

    findings: tuple[Finding, ...] = ()
    passed: tuple[Passed, ...] = ()
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        """Return whether anything found stops the deployment being used."""
        return not any(finding.is_blocking for finding in self.findings)

    def ordered(self) -> tuple[Finding, ...]:
        """Return the findings most-blocking first, then alphabetically.

        FR-008. The second key is not cosmetic: the checks finish in whatever
        order their dependencies answer, so without it the same deployment
        produces a differently ordered report each run and nobody can diff two.
        """
        return tuple(sorted(self.findings, key=lambda finding: (finding.weight, finding.check)))

    def blocking(self) -> tuple[Finding, ...]:
        """Return only what stops the deployment doing something it is for."""
        return tuple(finding for finding in self.ordered() if finding.is_blocking)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console, the CLI and a bundle read."""
        return {
            "ok": self.ok,
            "findings": [finding.to_record() for finding in self.ordered()],
            "passed": [entry.to_record() for entry in self.passed],
            "duration_seconds": round(self.duration_seconds, 3),
        }

    def summary(self) -> str:
        """Return the block a terminal prints.

        A passing check reports in one line. A failing one reports every problem
        it found — that is FR-008 — and an operator who has to act on four things
        would rather read four lines than run the check four times.
        """
        if not self.findings:
            return f"self-check: {len(self.passed)} checks, nothing to report"
        lines = [
            f"self-check: {len(self.findings)} problem(s), most blocking first",
            *(f"  {finding}" for finding in self.ordered()),
        ]
        if self.passed:
            lines.append(f"  ({len(self.passed)} other checks found nothing)")
        return "\n".join(lines)


async def run_checks(
    checks: Sequence[Check],
    *,
    timeout_seconds: float = SELF_CHECK_TIMEOUT_SECONDS,
) -> SelfCheckReport:
    """Run every check concurrently and return one report.

    Concurrently rather than in sequence: nine checks each allowed five seconds
    is forty-five seconds in the worst case, which is past the budget before the
    first one has answered. Run together, the worst case is one timeout.
    """
    loop = asyncio.get_running_loop()
    started = loop.time()

    outcomes = await asyncio.gather(
        *(_bounded(check, timeout_seconds) for check in checks),
    )

    findings: list[Finding] = []
    passed: list[Passed] = []
    for outcome in outcomes:
        if outcome.findings:
            findings.extend(outcome.findings)
        else:
            passed.append(Passed(check=outcome.check, detail=outcome.detail))

    return SelfCheckReport(
        findings=tuple(findings),
        passed=tuple(passed),
        duration_seconds=loop.time() - started,
    )


async def _bounded(check: Check, timeout_seconds: float) -> CheckOutcome:
    """Run one check, turning both a timeout and a crash into a finding.

    Nothing escapes. A self-check that propagated the first exception would
    report nothing about the eight dependencies it never reached, which is the
    opposite of what a single-pass check is for.
    """
    try:
        return await asyncio.wait_for(check.run(), timeout=timeout_seconds)
    except TimeoutError:
        return CheckOutcome.problem(
            check.name,
            problem=(
                f"{check.name} did not answer within {timeout_seconds:g}s, so it is "
                f"either unreachable or too slow to be usable"
            ),
            action=(
                f"check that {check.name} is running and reachable from this host, then "
                f"run the self-check again"
            ),
            blocks=BLOCKS_ONE_FEATURE,
        )
    except Exception as error:  # noqa: BLE001 — reported, never propagated
        return CheckOutcome.problem(
            check.name,
            problem=f"{check.name} raised {type(error).__name__}: {error}",
            action=(
                f"read the message above — it comes from {check.name} itself — and fix "
                f"what it names, then run the self-check again"
            ),
            blocks=BLOCKS_ONE_FEATURE,
        )


# --- The checks -----------------------------------------------------------------


def store_checks(gateway: PersistenceGateway) -> tuple[Check, ...]:
    """Return the database and schema checks over ``gateway``.

    Two checks rather than one, because "the database is up and the schema is
    behind" and "the database is down" lead to different actions and only one of
    them is fixed by starting a container.
    """

    async def database() -> CheckOutcome:
        health = await gateway.health()
        if health.connected:
            return CheckOutcome.fine(CHECK_DATABASE, detail="connected")
        return CheckOutcome.problem(
            CHECK_DATABASE,
            problem=(
                "the database did not answer: " + ("; ".join(health.reasons) or "no reason given")
            ),
            action=(
                "start PostgreSQL, or point NINJASRE_DATABASE_URL at one that is running "
                "and reachable from this host"
            ),
            blocks=BLOCKS_EVERYTHING,
        )

    async def schema() -> CheckOutcome:
        health = await gateway.health()
        return _schema_outcome(health)

    return (
        Check(name=CHECK_DATABASE, run=database),
        Check(name=CHECK_SCHEMA, run=schema),
    )


def _schema_outcome(health: StoreHealth) -> CheckOutcome:
    """Return what the store's migration state means for an operator."""
    if not health.connected:
        return CheckOutcome.problem(
            CHECK_SCHEMA,
            problem="the schema cannot be read because the database is not answering",
            action="fix the database first; the schema check has nothing to read until then",
            blocks=BLOCKS_EVERYTHING,
        )
    migrations = health.migrations
    if migrations is None:
        return CheckOutcome.problem(
            CHECK_SCHEMA,
            problem="the database answered but reports no schema version at all",
            action=(
                "run the migrations — start the deployment with migrations enabled, or run "
                "the migration job out of band"
            ),
            blocks=BLOCKS_EVERYTHING,
        )
    if migrations.is_current:
        return CheckOutcome.fine(CHECK_SCHEMA, detail=f"at {migrations.head_revision}")
    return CheckOutcome.problem(
        CHECK_SCHEMA,
        problem=(
            f"the schema is at {migrations.applied_revision or 'an empty database'} and this "
            f"release expects {migrations.head_revision}"
        ),
        action=(
            "restart with migrations enabled, or run the migration job; this release refuses "
            "to serve traffic against a schema it was not written for"
        ),
        blocks=BLOCKS_EVERYTHING,
        detail={
            "applied": migrations.applied_revision,
            "expected": migrations.head_revision,
        },
    )


def disk_space_check(
    *,
    free_bytes: Callable[[], int] | None = None,
    minimum: int = MINIMUM_FREE_DISK_BYTES,
    path: str = ".",
) -> Check:
    """Return the check that the disk has room for a day of investigations."""

    def measure() -> int:
        return shutil.disk_usage(path).free

    read = free_bytes or measure

    async def body() -> CheckOutcome:
        free = read()
        if free >= minimum:
            return CheckOutcome.fine(CHECK_DISK_SPACE, detail=f"{human_bytes(free)} free")
        return CheckOutcome.problem(
            CHECK_DISK_SPACE,
            problem=(
                f"{human_bytes(free)} free, below the {human_bytes(minimum)} an "
                f"investigation's evidence and the database's write-ahead log need"
            ),
            action=(
                "free space on this volume, or move the database's data directory to one "
                "with room; below this the two start competing and writes begin to fail"
            ),
            blocks=BLOCKS_INVESTIGATION,
            detail={"free_bytes": free, "minimum_bytes": minimum},
        )

    return Check(name=CHECK_DISK_SPACE, run=body)


def clock_skew_check(
    *,
    local: Callable[[], datetime] | None = None,
    reference: Callable[[], datetime] | None = None,
    tolerance_seconds: float = MAXIMUM_CLOCK_SKEW_SECONDS,
) -> Check:
    """Return the check that this host's clock agrees with its reference.

    With no reference supplied there is nothing to compare against and the check
    reports that rather than inventing a comparison — a check that always passes
    because it checks nothing is worse than one that is honestly absent.
    """
    now = local or (lambda: datetime.now(UTC))

    async def body() -> CheckOutcome:
        if reference is None:
            return CheckOutcome.fine(
                CHECK_CLOCK_SKEW, detail="no reference clock configured; nothing to compare"
            )
        skew = abs((reference() - now()).total_seconds())
        if skew <= tolerance_seconds:
            return CheckOutcome.fine(CHECK_CLOCK_SKEW, detail=f"{skew:.0f}s from the reference")
        return CheckOutcome.problem(
            CHECK_CLOCK_SKEW,
            problem=(
                f"this host's clock is {skew:.0f}s from its reference, beyond the "
                f"{tolerance_seconds:.0f}s a token's expiry comparison tolerates"
            ),
            action=(
                "enable NTP on this host, or correct the clock; beyond this, tokens issued "
                "here are rejected elsewhere before they have been used"
            ),
            blocks=BLOCKS_ONE_FEATURE,
            detail={"skew_seconds": skew, "tolerance_seconds": tolerance_seconds},
        )

    return Check(name=CHECK_CLOCK_SKEW, run=body)


def credential_proxy_check(probe: Callable[[], Any] | None = None) -> Check:
    """Return the check that the credential proxy is reachable.

    ``probe`` is awaited and its truth is the answer. It is injected because
    where the proxy lives is a profile decision — in-process on the dev profile,
    a container on the standard one — and this module must not know which.
    """

    async def body() -> CheckOutcome:
        if probe is None:
            return CheckOutcome.problem(
                CHECK_CREDENTIAL_PROXY,
                problem=(
                    "no credential proxy is wired, so every authenticated integration call "
                    "would have to carry a secret the agent must never see"
                ),
                action=(
                    "set NINJASRE_CREDENTIAL_PROXY_URL to the proxy this deployment runs, or "
                    "use a profile that runs it in-process"
                ),
                blocks=BLOCKS_INVESTIGATION,
            )
        reachable = probe()
        if hasattr(reachable, "__await__"):
            reachable = await reachable
        if reachable:
            return CheckOutcome.fine(CHECK_CREDENTIAL_PROXY, detail="reachable")
        return CheckOutcome.problem(
            CHECK_CREDENTIAL_PROXY,
            problem="the credential proxy is configured but did not answer",
            action=(
                "start the proxy, or correct NINJASRE_CREDENTIAL_PROXY_URL; without it no "
                "integration can authenticate and every investigation stops at its first tool"
            ),
            blocks=BLOCKS_INVESTIGATION,
        )

    return Check(name=CHECK_CREDENTIAL_PROXY, run=body)


def model_provider_check(verify: Callable[[], Any] | None = None) -> Check:
    """Return the check that a model this deployment can actually use is configured.

    ``verify`` returns a ``ModelVerdict`` (see ``core.llm.verification``). It is
    injected rather than imported and called, because verifying a provider makes
    real calls against the operator's endpoint and the self-check must be able to
    run without spending anything.
    """

    async def body() -> CheckOutcome:
        if verify is None:
            return CheckOutcome.problem(
                CHECK_MODEL_PROVIDER,
                problem="no model provider is configured, so nothing can reason about anything",
                action=(
                    "set NINJASRE_LLM_PROVIDER and the credential it needs, then run the "
                    "self-check again — it will verify tool calling rather than assume it"
                ),
                blocks=BLOCKS_INVESTIGATION,
            )
        verdict = verify()
        if hasattr(verdict, "__await__"):
            verdict = await verdict
        if verdict.satisfied:
            return CheckOutcome.fine(CHECK_MODEL_PROVIDER, detail=verdict.summary_line)
        return CheckOutcome.problem(
            CHECK_MODEL_PROVIDER,
            problem=verdict.limitation,
            action=verdict.remedy,
            blocks=BLOCKS_INVESTIGATION,
            detail={"provider": verdict.provider_id, "model": verdict.model_id},
        )

    return Check(name=CHECK_MODEL_PROVIDER, run=body)


def integrations_check(report: Callable[[], Any] | None = None) -> Check:
    """Return the check that each configured integration holds a usable credential.

    One finding per unusable integration rather than one for all of them. They
    are fixed one at a time and an operator reading "3 integrations unhealthy"
    has to go and find out which.
    """

    async def body() -> CheckOutcome:
        if report is None:
            return CheckOutcome.fine(CHECK_INTEGRATIONS, detail="no integrations configured yet")
        health = report()
        if hasattr(health, "__await__"):
            health = await health
        findings = [
            Finding(
                check=CHECK_INTEGRATIONS,
                problem=(
                    f"{entry.integration}'s credential is {entry.state}, so calls to it "
                    f"would fail at the proxy rather than at the vendor"
                ),
                action=(
                    f"run 'ninjasre integrations configure {entry.integration}' and supply a "
                    f"current credential"
                ),
                blocks=BLOCKS_ONE_FEATURE,
                detail={"integration": entry.integration, "state": str(entry.state)},
            )
            for entry in health.unusable
        ]
        if findings:
            return CheckOutcome.problems(CHECK_INTEGRATIONS, findings)
        return CheckOutcome.fine(
            CHECK_INTEGRATIONS, detail=f"{len(health.entries)} configured and usable"
        )

    return Check(name=CHECK_INTEGRATIONS, run=body)


def investigation_runtime_check(composed: Callable[[], Any] | None = None) -> Check:
    """Return the check that something here can actually drive an investigation.

    The one dependency that leaves no trace on any screen. An account, a
    provider key, a resource in the estate — all of them are visible from the
    console; a process with nothing composed to run a ReAct loop looks exactly
    like one that has, right up to the moment somebody presses Investigate and
    the run fails before it starts.

    Neither sentence names a setting of the process. The console renders this
    report, and a finding whose text is a deploy instruction puts the
    environment variable back on the screen the failure translation exists to
    keep it off. The variable is named where it belongs: in the refusal the
    entry point raises, and in the deployment documentation.
    """

    async def body() -> CheckOutcome:
        # Not supplied and answered-no are one finding here, unlike the
        # scheduler's two: a runtime nobody composed and a runtime that reports
        # itself absent are the same deployment from an operator's chair.
        answered: Any = composed() if composed is not None else False
        if hasattr(answered, "__await__"):
            answered = await answered
        if answered:
            return CheckOutcome.fine(
                CHECK_INVESTIGATION_RUNTIME, detail="an investigation has something to run in"
            )
        return CheckOutcome.problem(
            CHECK_INVESTIGATION_RUNTIME,
            problem=(
                "nothing in this deployment can drive an investigation — a model provider "
                "and an integration may both be configured, and the part that puts them "
                "together has not been supplied to this process"
            ),
            action=(
                "whoever operates this deployment supplies the investigation runtime; "
                "until they do, starting an investigation fails immediately and every "
                "screen fed by one stays empty"
            ),
            blocks=BLOCKS_INVESTIGATION,
        )

    return Check(name=CHECK_INVESTIGATION_RUNTIME, run=body)


def scheduler_check(running: Callable[[], Any] | None = None) -> Check:
    """Return the check that scheduled work is being claimed by something."""

    async def body() -> CheckOutcome:
        if running is None:
            return CheckOutcome.problem(
                CHECK_SCHEDULER,
                problem=(
                    "no scheduler is running, so nothing on a schedule will ever run — "
                    "recurring investigations, retention sweeps and verification all stop"
                ),
                action=(
                    "run the application process rather than only the gateway; the scheduler "
                    "is in-process on the dev and standard profiles"
                ),
                blocks=BLOCKS_ONE_FEATURE,
            )
        alive = running()
        if hasattr(alive, "__await__"):
            alive = await alive
        if alive:
            return CheckOutcome.fine(CHECK_SCHEDULER, detail="claiming work")
        return CheckOutcome.problem(
            CHECK_SCHEDULER,
            problem="the scheduler is wired but is not claiming work",
            action=(
                "check the application log for the reason it stopped, then restart the "
                "deployment; scheduled work is queued and will run once it is claiming again"
            ),
            blocks=BLOCKS_ONE_FEATURE,
        )

    return Check(name=CHECK_SCHEDULER, run=body)


def observer_check(running: Callable[[], Any] | None = None) -> Check:
    """Return the check that something is watching the estate.

    Degrading rather than blocking. A deployment fed by webhooks alone is a
    reasonable design and the observer is genuinely optional there — but an
    operator who thought they had continuous observation and does not should be
    told, which is what a degrading finding is for.
    """

    async def body() -> CheckOutcome:
        if running is None:
            return CheckOutcome.problem(
                CHECK_OBSERVER,
                problem=(
                    "nothing is observing the estate, so this deployment only ever reacts "
                    "to an alert somebody else sent it"
                ),
                action=(
                    "configure at least one observation source, or accept that incidents "
                    "arrive by webhook only"
                ),
                blocks=DEGRADES,
            )
        alive = running()
        if hasattr(alive, "__await__"):
            alive = await alive
        if alive:
            return CheckOutcome.fine(CHECK_OBSERVER, detail="polling")
        return CheckOutcome.problem(
            CHECK_OBSERVER,
            problem="the observer is configured but is not polling",
            action=(
                "check the application log for the poller's last error, then restart the deployment"
            ),
            blocks=BLOCKS_ONE_FEATURE,
        )

    return Check(name=CHECK_OBSERVER, run=body)


#: Every check this module can produce, by the name the constants tier declares.
#: A test asserts the two sets are equal, so a check added here without a name
#: there — or a name declared and never implemented — fails the build.
CHECK_BUILDERS: Mapping[str, Callable[..., Any]] = {
    CHECK_DATABASE: store_checks,
    CHECK_SCHEMA: store_checks,
    CHECK_CREDENTIAL_PROXY: credential_proxy_check,
    CHECK_MODEL_PROVIDER: model_provider_check,
    CHECK_INVESTIGATION_RUNTIME: investigation_runtime_check,
    CHECK_INTEGRATIONS: integrations_check,
    CHECK_SCHEDULER: scheduler_check,
    CHECK_OBSERVER: observer_check,
    CHECK_DISK_SPACE: disk_space_check,
    CHECK_CLOCK_SKEW: clock_skew_check,
}


def deployment_checks(
    gateway: PersistenceGateway,
    *,
    credential_proxy: Callable[[], Any] | None = None,
    model_provider: Callable[[], Any] | None = None,
    investigation_runtime: Callable[[], Any] | None = None,
    integrations: Callable[[], Any] | None = None,
    scheduler: Callable[[], Any] | None = None,
    observer: Callable[[], Any] | None = None,
    free_bytes: Callable[[], int] | None = None,
    reference_clock: Callable[[], datetime] | None = None,
) -> tuple[Check, ...]:
    """Return the full set FR-007 lists, for a deployment that has a store.

    Every collaborator past the store is optional, and an absent one produces a
    finding rather than a skipped check. That is the difference between "we did
    not look" and "there is nothing there", and only one of them is a green tick
    somebody should trust.
    """
    return (
        *store_checks(gateway),
        credential_proxy_check(credential_proxy),
        model_provider_check(model_provider),
        investigation_runtime_check(investigation_runtime),
        integrations_check(integrations),
        scheduler_check(scheduler),
        observer_check(observer),
        disk_space_check(free_bytes=free_bytes),
        clock_skew_check(reference=reference_clock),
    )


async def self_check(
    gateway: PersistenceGateway,
    *,
    timeout_seconds: float = SELF_CHECK_TIMEOUT_SECONDS,
    **collaborators: Any,
) -> SelfCheckReport:
    """Run every check FR-007 lists and return one ordered report."""
    return await run_checks(
        deployment_checks(gateway, **collaborators), timeout_seconds=timeout_seconds
    )


__all__ = [
    "CHECK_BUILDERS",
    "Check",
    "CheckBody",
    "CheckOutcome",
    "Finding",
    "Passed",
    "SelfCheckReport",
    "clock_skew_check",
    "credential_proxy_check",
    "deployment_checks",
    "disk_space_check",
    "human_bytes",
    "integrations_check",
    "investigation_runtime_check",
    "model_provider_check",
    "observer_check",
    "run_checks",
    "scheduler_check",
    "self_check",
    "store_checks",
]

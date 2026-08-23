"""Wiring the desk that turns a proposed write into a stored approval.

Everything a remediation needs has existed for some time. The gate that stops an
unapproved write, the builder that assembles what a reviewer reads, the factory
that derives the undo before the change, the executor that runs it inside a
sandbox, the component registry, the approval routes, and the three tables they
write into. A sweep of this repository for a constructed gate returned tests,
contract tests and the mock data plane — which is to say the whole mechanism was
written and no deployment had it. Every investigation stopped at the diagnosis,
and it stopped there because nothing built the gate rather than because a policy
said to.

**Composed here rather than in the synchronous root.** The desk needs a
persistence handle, a tenant scope and the team's resolved configuration. The
synchronous root knows the process environment and nothing else, which is the
same reason the deep verifier and the discovery sources are composed here.

**One desk, two consumers.** The loop reaches it to propose and the approval
route reaches it to carry a granted decision out. It is one object referenced
twice, never two constructions: two would be two executors, two readings of the
emergency stop, and two audit trails that could disagree about what ran.

**A deployment that cannot carry a write composes nothing, and says which piece
is missing.** Degrading silently here is worse than not composing at all,
because "this deployment decided not to act" and "this deployment does not know
how to act" are opposite facts that look identical from outside.

**The autonomy gate is a builder, not a built gate.** Posture lives in
configuration and a person changes it through routes that already exist, so a
gate constructed at boot would decide with yesterday's posture. It is built
through the same service the published explanation uses, which is what stops a
screen predicting one thing while the gate does another.

**Nothing here holds a credential.** The executor reaches a control plane
through the credential proxy like every other authenticated call, and what
crosses this module is an address and a tenant.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation import registry as component_registry
from platform.approvals.models import ChangeType
from platform.approvals.policy import DEFAULT_POLICY
from platform.approvals.service import ApprovalService
from platform.autonomy.decision import AutonomyGate
from platform.autonomy.policy import PolicySet
from platform.autonomy.service import AutonomyService
from platform.config_service.service import ConfigService
from platform.identity.audit.recorder import AuditRecorder
from platform.observability.logging import get_logger
from platform.persistence.ports import TenantScope
from platform.persistence.ports.signal_store import Signal
from platform.remediation.audit import RemediationAuditor
from platform.remediation.components import ComponentRegistry
from platform.remediation.errors import RemediationError
from platform.remediation.execution import (
    RemediationApplier,
    RemediationExecutor,
    SandboxIsolation,
)
from platform.remediation.gating import GatingPolicy, RemediationGate, RunContext
from platform.remediation.guards import ClosedLoopGuards
from platform.remediation.history import LedgerEffectiveness
from platform.remediation.models import RemediationAction
from platform.remediation.obligations import LedgerVerification
from platform.remediation.request import RequestBuilder
from platform.remediation.rollback.generator import PlanFactory
from platform.remediation.verification import OutcomeVerification
from platform.sandbox.errors import UnknownSandboxProfile
from platform.sandbox.selection import resolve_profile
from platform.sandbox.spec import EgressPolicy, SandboxProfile, SandboxSpec

logger = get_logger(__name__)

#: What a sandbox and an audit row are told is asking, when the action itself
#: names no team — an operator-triggered write has no incident behind it and
#: still has to be attributable to something rather than to an empty string.
REMEDIATION_SCOPE_CAPABILITY = "remediation.execute"

#: What an egress policy names when this deployment composed no credential
#: proxy. An unroutable loopback rather than an omission, because the policy
#: type refuses to describe a sandbox with nowhere to authenticate through — and
#: a sandbox that can reach vendors and not the proxy is one that has reinvented
#: putting credentials in the agent.
_LOOPBACK_PROXY = "http://127.0.0.1:0"


@dataclass(frozen=True, slots=True)
class RemediationDesk:
    """Everything this deployment needs to take a write from proposal to execution.

    Held as one value rather than as six fields on the gateway state, because
    every one of them is useless without the others and a partially wired set
    would be a deployment that proposes and cannot execute — the exact
    half-composed state this module exists to make impossible.
    """

    requests: RequestBuilder
    executor: RemediationExecutor
    policy: GatingPolicy
    #: How the posture is resolved at the moment a write is decided, keyed by
    #: the team the run belongs to. A callable rather than a built gate: see the
    #: module docstring.
    autonomy_of: Callable[[str], Awaitable[AutonomyGate]]
    #: Which capabilities this deployment has all four components for. A write
    #: outside this set cannot be read, planned, applied or verified, so
    #: offering it to a turn spends a schema slot on a certain refusal.
    capabilities: frozenset[str]
    kill_switch: Any
    guards_of: Callable[[str], Any] | None = None

    def handles(self, capability: str) -> bool:
        """Return whether this deployment could carry ``capability`` out."""
        return capability in self.capabilities

    def gate_for(self, run: RunContext) -> RemediationGate:
        """Return the gate for one investigation, carrying that run's context.

        Per run rather than per process. The context names who asked and for
        which team; a gate built once at boot would carry whichever run happened
        to build it, and the second concurrent investigation would propose
        changes attributed to the first person.
        """
        team = run.team_node_id or ""
        return RemediationGate(
            requests=self.requests,
            executor=self.executor,
            kill_switch=self.kill_switch,
            guards=self.guards_of(team) if self.guards_of is not None else None,
            policy=self.policy,
            run=run,
            resolve_autonomy=lambda: self.autonomy_of(team),
        )


def unmet_for_remediation(state: Any) -> tuple[str, ...]:
    """Return what this deployment is missing before it can carry a write.

    Named rather than logged as a boolean, so a deployment that proposes nothing
    can say which piece an operator has to supply. Empty means the desk composes.
    """
    missing: list[str] = []

    if control_plane.current() is None:
        missing.append(
            "a control plane, so there is nothing for a write to change; an operator "
            "configures one before remediation is available"
        )

    try:
        profile = resolve_profile()
    except UnknownSandboxProfile as unknown:
        missing.append(f"a sandbox profile this deployment recognises ({unknown})")
    else:
        if _sandbox_for(profile) is None:
            missing.append(
                f"a sandbox this host can provision for the {profile.value} profile, "
                f"so no write could be run in isolation"
            )

    if getattr(state, "gateway", None) is None:
        missing.append("a persistence handle to write the approval and the plan through")

    return tuple(missing)


async def compose_remediation(
    state: Any, *, org_id: str, proxy_url: str = ""
) -> RemediationDesk | None:
    """Install the desk a write travels through, or install none and say why.

    Returns what was composed so a caller can log it. ``None`` is a working
    deployment: it proposes nothing above ``read_sensitive``, offers no write to
    a turn, and the line below names the piece that would change that.
    """
    unmet = unmet_for_remediation(state)
    if unmet:
        logger.info("remediation.desk_skipped", missing=list(unmet))
        return None

    scope = TenantScope(org_id=org_id)

    try:
        components = component_registry(known_signals=_known_signals(state))
    except RemediationError as refused:
        # A capability naming a signal nothing here emits fails at composition
        # rather than verifying against nothing for ever. The process still
        # comes up, because the console somebody would fix it from is served by
        # this same process.
        logger.warning("remediation.desk_skipped", missing=[str(refused)])
        return None

    isolation = _isolation(proxy_url=proxy_url)
    if isolation is None:
        logger.info("remediation.desk_skipped", missing=["a sandbox this host can provision"])
        return None

    recorder = AuditRecorder(gateway=state.gateway)
    approvals = ApprovalService(
        gateway=state.gateway,
        scope=scope,
        appliers={ChangeType.REMEDIATION: RemediationApplier(registry=components)},
        policy=DEFAULT_POLICY,
        recorder=recorder,
    )

    requests = RequestBuilder(
        registry=components,
        plans=PlanFactory(registry=components),
        approvals=approvals,
        gateway=state.gateway,
        scope=scope,
        history=LedgerEffectiveness(gateway=state.gateway, scope=scope),
    )

    executor = RemediationExecutor(
        registry=components,
        isolation=isolation,
        verification=OutcomeVerification(registry=components),
        # The process's own stop, never a fresh one: a switch constructed per
        # request is a switch that is never engaged when anything reads it.
        kill_switch=state.kill_switch,
        auditor=RemediationAuditor(scope=scope, recorder=recorder),
        obligations=LedgerVerification(
            gateway=state.gateway,
            scope=scope,
            signals=_StoredSignals(gateway=state.gateway, scope=scope),
            registry=components,
        ),
    )

    desk = RemediationDesk(
        requests=requests,
        executor=executor,
        policy=GatingPolicy.of_policy(DEFAULT_POLICY),
        autonomy_of=_autonomy_of(state, org_id=org_id),
        capabilities=frozenset(components.components),
        kill_switch=state.kill_switch,
        guards_of=_guards_of(state, components, org_id=org_id),
    )

    state.remediation = desk
    attach = getattr(state.investigator, "attach_remediation", None)
    if attach is not None:
        attach(desk)
    logger.info(
        "remediation.desk_composed",
        capabilities=len(desk.capabilities),
        profile=resolve_profile().value,
    )
    return desk


def _autonomy_of(state: Any, *, org_id: str) -> Callable[[str], Awaitable[AutonomyGate]]:
    """Return how this deployment resolves its posture at the moment of a decision.

    Through ``AutonomyService`` rather than by reading configuration here,
    because that is the one resolution the published explanation also uses. Two
    resolutions would be two answers, and the day they drifted a screen would
    predict a level the gate does not act on.
    """

    async def resolve(team_node_id: str) -> AutonomyGate:
        scope = TenantScope(org_id=org_id, team_node_id=team_node_id or None)
        service = AutonomyService(
            gateway=state.gateway,
            scope=scope,
            config=ConfigService(gateway=state.gateway, scope=scope, guardrails=state.guardrails),
            stop=state.kill_switch,
        )
        try:
            policies = await service.policy(team_node_id or org_id)
        except Exception as unreadable:  # noqa: BLE001 — an unread posture is never permission
            # The strictest reading of silence, and the reason is recorded. A
            # configuration that could not be read must not become permission.
            logger.warning(
                "remediation.posture_unreadable",
                team_node_id=team_node_id,
                error=str(unreadable),
            )
            policies = PolicySet()
        return service.gate(policies)

    return resolve


def _guards_of(state: Any, components: ComponentRegistry, *, org_id: str) -> Callable[[str], Any]:
    """Return what the closed loop knows about acting on a target unattended."""

    def guards(team_node_id: str) -> ClosedLoopGuards:
        return ClosedLoopGuards(
            gateway=state.gateway,
            scope=TenantScope(org_id=org_id, team_node_id=team_node_id or None),
            registry=components,
        )

    return guards


def _known_signals(state: Any) -> Sequence[str] | None:
    """Return what this deployment's observation sources produce, when it can say.

    ``None`` rather than an empty tuple for a deployment that cannot enumerate
    them, and the difference decides everything: an empty list refuses to
    register every capability that declares a signal, so a deployment that has
    not wired observation would be one that cannot remediate either. A metrics
    system serves whatever series it is asked for, so "which names exist" is not
    a question this side can answer without asking one — which is why the check
    is opt-in rather than a default, and why saying so here is better than
    passing a list somebody assembled by hand.
    """
    del state
    return None


@dataclass(frozen=True, slots=True)
class _StoredSignals:
    """Reads the newest sample of each named signal through its own unit of work.

    What a long-lived executor holds. The signal store is a repository bound to
    one transaction, and the executor outlives every transaction in the process.
    """

    gateway: Any
    scope: TenantScope

    async def latest(
        self,
        *,
        names: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
    ) -> tuple[Signal, ...]:
        """Return the newest sample per name and resource, however old it is."""
        async with self.gateway.begin(self.scope) as uow:
            return await uow.signals.latest(names=names, resource_ids=resource_ids)


def _isolation(*, proxy_url: str) -> SandboxIsolation | None:
    """Return the isolation every write runs inside, or ``None`` when there is none."""
    try:
        profile = resolve_profile()
    except UnknownSandboxProfile:
        return None
    sandbox = _sandbox_for(profile)
    if sandbox is None:
        return None
    return SandboxIsolation(
        sandbox=sandbox,
        spec_for=_spec_for(proxy_url=proxy_url),
        proxy_url=proxy_url,
    )


def _spec_for(*, proxy_url: str) -> Callable[[RemediationAction], SandboxSpec]:
    """Return how one action is turned into the sandbox it runs in.

    The investigation is the tenant of its own sandbox, which is what makes an
    orphan recognisable to the reaper and what stops two runs sharing one.
    """

    def specification(action: RemediationAction) -> SandboxSpec:
        return SandboxSpec(
            org_id=action.target.node_id or action.team_node_id or REMEDIATION_SCOPE_CAPABILITY,
            team_id=action.team_node_id or REMEDIATION_SCOPE_CAPABILITY,
            investigation_id=action.run_id or action.action_id,
            egress=EgressPolicy(proxy_url=proxy_url or _LOOPBACK_PROXY),
        )

    return specification


def _sandbox_for(profile: SandboxProfile) -> Any:
    """Return the provisioner for ``profile`` on this host, or ``None``.

    ``None`` is a real answer and never a fallback to a lighter profile. A
    fallback is what gets switched on during an outage and never switched back.
    """
    try:
        if profile is SandboxProfile.PROCESS:
            from platform.sandbox.profiles.process.runner import ProcessSandbox

            return ProcessSandbox()
        if profile is SandboxProfile.KUBERNETES:
            from platform.sandbox.profiles.kubernetes.engine import in_cluster
            from platform.sandbox.profiles.kubernetes.runner import KubernetesSandbox

            return KubernetesSandbox(api=in_cluster())
        from platform.sandbox.profiles.container.engine import DockerEngine
        from platform.sandbox.profiles.container.runner import ContainerSandbox

        return ContainerSandbox(engine=DockerEngine())
    except Exception as unavailable:  # noqa: BLE001 — an absent runtime is a fact, not a crash
        logger.info(
            "remediation.sandbox_unavailable", profile=profile.value, error=str(unavailable)
        )
        return None


__all__ = [
    "REMEDIATION_SCOPE_CAPABILITY",
    "RemediationDesk",
    "compose_remediation",
    "unmet_for_remediation",
]

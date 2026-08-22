"""The proxy itself: resolve, inject, forward — and the order that matters.

Everything else in this package is a piece. This is the sequence, and the
sequence is the design:

1. **Rate limit.** Before anything else, because a tenant past its limit should
   cost the proxy one dictionary lookup, not a vault read.
2. **Find the rule.** An integration with no declared injection rule has no
   sanctioned way to authenticate, so the call stops rather than going out bare.
3. **Check the host.** The rule's ``hosts`` is the allow-list (FR-009), and it
   runs *before* the vault. A request that acquired a hostile URL — the
   realistic route being a prompt-injected log line — must not be able to make
   the proxy decrypt anything.
4. **Resolve.** Team first, organisation as the single fallback, scoped to the
   requesting tenant (FR-007, SC-007).
5. **Refresh if the credential is about to expire** (FR-013).
6. **Inject.** The declared injections, in declared order.
7. **Send**, and on an expiry-shaped rejection, refresh and send exactly once
   more.
8. **Audit**, whatever happened (FR-019).

**There is no step that skips steps.** No configuration flag, no environment
variable, no "degraded mode" (FR-010). The engine has one public method and it
runs the whole sequence; the way to have a proxy that does less is to not have
one, and then nothing works, which is the intended failure. A bypass is exactly
the switch that gets flipped at 03:00 during an outage and never flipped back —
availability is solved by running the proxy next to the agent, not by having a
path around it.

The credential exists in memory from step 4 to step 7 and is referenced by
nothing afterwards. It is never returned, never logged, never put in the audit
record, and never handed to anything above this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from config.constants.security import (
    CREDENTIAL_EXPIRY_RETRY_ATTEMPTS,
    CREDENTIAL_PROXY_TIMEOUT_SECONDS,
)
from platform.credentials.errors import CredentialNotConfigured, UnknownIntegration
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy import egress
from platform.credentials.proxy.audit import ResolutionAuditor, ResolutionRecord
from platform.credentials.proxy.errors import (
    CredentialExpired,
    CredentialFieldsMissing,
    CredentialUnavailable,
    CredentialUnreadable,
    IntegrationNotDeclared,
    ProxyError,
    RefreshFailed,
    UpstreamUnreachable,
)
from platform.credentials.proxy.injection import InjectionRule, InjectionRuleRegistry
from platform.credentials.proxy.model import (
    OutboundRequest,
    OutboundResponse,
    OutboundSender,
    ProxyRequest,
)
from platform.credentials.proxy.rate_limit import TenantRateLimiter
from platform.credentials.proxy.refresh import (
    CredentialRefresher,
    is_expiry_failure,
    needs_refresh,
)
from platform.credentials.proxy.resolution import CredentialResolver, ResolvedCredential
from platform.observability.logging import get_logger
from platform.persistence.errors import CredentialUndecryptable
from platform.persistence.ports import AuditOutcome, TenantScope

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProxyHealth:
    """What the proxy can say about itself without revealing anything (FR-020)."""

    ready: bool
    integrations: tuple[str, ...]
    tenants_in_window: int
    detail: str = ""

    def to_record(self) -> dict[str, object]:
        """Return the health payload the internal API serves."""
        return {
            "ready": self.ready,
            "integrations": list(self.integrations),
            "tenants_in_window": self.tenants_in_window,
            "detail": self.detail,
        }


class ProxyEngine:
    """Resolves, injects, and forwards. The only component that reads a secret.

    Constructed once per process and shared. Everything it holds is either
    stateless or a bounded counter, so the same instance serves the in-process
    mount in the ``dev`` profile and the standalone service in ``standard`` —
    which is what makes FR-011's "identical behaviour" a fact about the object
    graph rather than a promise about two implementations.
    """

    __slots__ = (
        "_auditor",
        "_clock",
        "_limiter",
        "_refresher",
        "_resolver",
        "_rules",
        "_sender",
        "_timeout_seconds",
    )

    def __init__(
        self,
        *,
        resolver: CredentialResolver,
        rules: InjectionRuleRegistry,
        sender: OutboundSender,
        auditor: ResolutionAuditor,
        limiter: TenantRateLimiter | None = None,
        refresher: CredentialRefresher | None = None,
        timeout_seconds: float = CREDENTIAL_PROXY_TIMEOUT_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._resolver = resolver
        self._rules = rules
        self._sender = sender
        self._auditor = auditor
        self._limiter = limiter if limiter is not None else TenantRateLimiter()
        self._refresher = refresher
        self._timeout_seconds = timeout_seconds
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    @property
    def rules(self) -> InjectionRuleRegistry:
        """Return the declared injection rules, for health and verification."""
        return self._rules

    @property
    def resolver(self) -> CredentialResolver:
        """Return the resolver, for the health check's metadata-only reads."""
        return self._resolver

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Authenticate ``request`` and return the vendor's answer.

        Raises a ``ProxyError`` subclass — never a bare exception and never a
        synthetic success — for anything that stopped the call before the
        vendor saw it. Every outcome, including every refusal, is audited.
        """
        record = ResolutionRecord(
            org_id=request.org_id,
            team_id=request.team_id,
            integration=request.integration,
            capability=request.capability,
            outcome=AuditOutcome.DENIED,
        )
        try:
            response, record = await self._forward(request, record)
        except ProxyError as error:
            await self._audit(record, reason=error)
            raise
        await self._audit(record)
        return response

    async def health(self) -> ProxyHealth:
        """Return readiness and what is declared, with no credential material."""
        return ProxyHealth(
            ready=True,
            integrations=self._rules.integrations(),
            tenants_in_window=len(self._limiter.snapshot()),
        )

    # -- the sequence ---------------------------------------------------------

    async def _forward(
        self,
        request: ProxyRequest,
        record: ResolutionRecord,
    ) -> tuple[OutboundResponse, ResolutionRecord]:
        """Run the whole sequence, returning the response and the audit record."""
        self._limiter.check(request.org_id, integration=request.integration)

        rule = self._rule_for(request.integration)
        host = egress.enforce(rule, request.url)
        record = replace(record, host=host)

        handle = CredentialHandle(integration=request.integration, team_id=request.team_id)
        credential = await self._resolve(request, rule, handle)
        if credential is not None:
            # Now that it is known something will be injected, the connection has
            # to be one it is safe to inject over. A request going out bare —
            # a self-hosted vendor with no authentication of its own — reaches
            # this line with nothing to protect and is not held to it.
            egress.refuse_credential_in_clear(rule, request.url)
            record = replace(record, handle=credential.handle.qualified, version=credential.version)

            now = self._clock()
            if needs_refresh(credential.expires_at, now):
                credential = await self._refresh(request, credential)
        else:
            record = replace(record, handle=handle.qualified)

        response = await self._send(request, rule, credential)
        if credential is not None and self._can_retry_expiry(rule, response.status_code):
            response = await self._retry_after_refresh(request, rule, credential)

        return response, replace(record, outcome=AuditOutcome.ALLOWED)

    def _rule_for(self, integration: str) -> InjectionRule:
        """Return the injection rule for ``integration``, or refuse the call."""
        try:
            return self._rules.get(integration)
        except UnknownIntegration as error:
            raise IntegrationNotDeclared(integration, known=error.known) from error

    async def _resolve(
        self,
        request: ProxyRequest,
        rule: InjectionRule,
        handle: CredentialHandle,
    ) -> ResolvedCredential | None:
        """Return the credential for ``handle``, or ``None`` if ``rule`` allows going without one.

        ``None`` only ever comes from ``rule.credential_optional`` meeting a
        genuine absence (``CredentialNotConfigured``). A credential that
        exists but cannot be read is still ``CredentialUnreadable`` — the
        optional path is for a vendor with no auth, not for tolerating a
        broken vault.
        """
        scope = TenantScope(org_id=request.org_id, team_node_id=request.team_id or None)
        try:
            return await self._resolver.resolve(scope, handle)
        except CredentialNotConfigured as error:
            if rule.credential_optional:
                return None
            raise CredentialUnavailable(
                request.integration,
                handle=handle.qualified,
                org_id=request.org_id,
                team_id=request.team_id,
            ) from error
        except CredentialUndecryptable as error:
            raise CredentialUnreadable(request.integration, handle=handle.qualified) from error

    async def _refresh(
        self,
        request: ProxyRequest,
        credential: ResolvedCredential,
    ) -> ResolvedCredential:
        """Return ``credential`` reissued, or fail the call saying why."""
        if self._refresher is None:
            raise CredentialExpired(request.integration, handle=credential.handle.qualified)
        try:
            refreshed = await self._refresher.refresh(request.integration, credential.values)
        except Exception as error:  # noqa: BLE001 — every vendor fails differently
            raise RefreshFailed(request.integration, cause=type(error).__name__) from error
        return credential.with_values(refreshed.values, expires_at=refreshed.expires_at)

    async def _send(
        self,
        request: ProxyRequest,
        rule: InjectionRule,
        credential: ResolvedCredential | None,
    ) -> OutboundResponse:
        """Inject the credential and put the request on the wire."""
        injected = self._inject(request.outbound(), rule, credential)
        try:
            return await self._sender.send(injected, timeout_seconds=self._timeout_seconds)
        except ProxyError:
            raise
        except Exception as error:  # noqa: BLE001 — a transport fails how it likes
            raise UpstreamUnreachable(
                request.integration,
                host=injected.host,
                cause=type(error).__name__,
            ) from error

    def _inject(
        self,
        outbound: OutboundRequest,
        rule: InjectionRule,
        credential: ResolvedCredential | None,
    ) -> OutboundRequest:
        """Return ``outbound`` with the declared injections applied.

        ``credential`` is ``None`` only when the rule declared itself
        optional and none was configured, and then the request goes out
        unchanged. A field the rule reads and a credential that *did*
        resolve does not carry is still a declaration error, and it still
        fails here rather than sending a request with a missing header that
        the vendor answers with an unexplainable 401.
        """
        if credential is None:
            return outbound
        missing = sorted(set(rule.required_fields()) - set(credential.values))
        if missing:
            raise CredentialFieldsMissing(
                rule.integration, handle=credential.handle.qualified, fields=missing
            )
        return rule.apply(outbound, credential.values, now=self._clock())

    def _can_retry_expiry(self, rule: InjectionRule, status_code: int) -> bool:
        """Return whether an expiry-shaped rejection is worth one more attempt.

        Three conditions, and the third is the one that is easy to leave out.
        Without a refresher there is nothing to retry *with*, so converting the
        vendor's 401 into a credential error would replace its answer with a
        guess — an operator whose IAM policy is wrong would be told their
        credential had expired. A deployment on long-lived AWS keys is exactly
        that case, and it is the common one.
        """
        return rule.refreshable and self._refresher is not None and is_expiry_failure(status_code)

    async def _retry_after_refresh(
        self,
        request: ProxyRequest,
        rule: InjectionRule,
        credential: ResolvedCredential,
    ) -> OutboundResponse:
        """Refresh and send once more (FR-013). Exactly once, whatever happens.

        The vendor rejected a credential that had not reached its declared
        expiry, which means the two clocks disagree or the vendor revoked early.
        A second attempt after a forced refresh fixes both; a third would be
        trying the same thing again.
        """
        logger.info(
            "credential.expiry_retry",
            integration=request.integration,
            capability=request.capability,
            attempts=CREDENTIAL_EXPIRY_RETRY_ATTEMPTS,
        )
        refreshed = await self._refresh(request, credential)
        return await self._send(request, rule, refreshed)

    async def _audit(
        self,
        record: ResolutionRecord,
        *,
        reason: ProxyError | None = None,
    ) -> None:
        """Write the audit line for this resolution, however it ended."""
        if reason is not None:
            record = replace(record, outcome=AuditOutcome.DENIED, reason=reason.reason)
        await self._auditor.record(record)


__all__ = [
    "ProxyEngine",
    "ProxyHealth",
]

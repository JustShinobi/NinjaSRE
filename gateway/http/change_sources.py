"""Composing "what changed" from the configuration tree, at startup.

A change source needs three things that live in three different places: a
setting (which repository, which vendor), a client the credential proxy can
build, and the estate that says which resource an alert is about. Only a
composition root has all three, and this is where the gateway's is.

**It is read from the configuration tree rather than from the environment.**
Which change sources a deployment has is a fact about the operator's estate,
and the configuration tree is where facts about the estate are edited — with
provenance, a preview, and an audit row. An environment variable would need a
restart and would leave no record of who changed it.

**Resolved at the root, once.** ``GatewayState`` is per process, and a source is
a client and a directory rather than a per-request decision. The root node is
the honest place to resolve it: a change source names a repository the whole
deployment shares, not a repository per team.

**A misconfiguration does not stop the gateway.** A vendor nothing can read is
logged and skipped, because the console somebody would fix it from is served by
the same process — and a deployment that refuses to start over one optional
setting is one nobody can correct.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from capabilities.tools.changes import binding
from gateway.http.state import GatewayState
from integrations._base.changes import GitHostChangeSource, UnsupportedGitHost
from platform.changes.correlation import views_of
from platform.changes.infra_apply import InfraApplySource
from platform.changes.models import ChangeWindow
from platform.changes.service import ChangeAnswer, ChangeInquiry
from platform.config_service.schema.policies import ChangeSourceSettings
from platform.config_service.service import ConfigService
from platform.estate.service import EstateService
from platform.observability.logging import get_logger
from platform.persistence.ports import TenantScope

logger = get_logger(__name__)


def change_sources_from(settings: ChangeSourceSettings) -> tuple[Any, ...]:
    """Return the change sources ``settings`` describes, in the order to ask them.

    The apply record first. It answers "did anybody actually apply this", which
    a commit listing cannot, and that is the evidence a reviewer wants at the
    top of the answer rather than buried under commits nobody deployed.

    Raises:
        UnsupportedGitHost: the configured vendor has no commit listing. Raised
            here, where the setting is read, rather than during the first
            investigation that needed it.
    """
    sources: list[Any] = []
    if settings.repository_path.strip():
        sources.append(InfraApplySource(root=Path(settings.repository_path.strip())))
    if settings.git_host.vendor.strip() and settings.git_host.repository.strip():
        sources.append(
            GitHostChangeSource(
                vendor=settings.git_host.vendor.strip(),
                repository=settings.git_host.repository.strip(),
            )
        )
    return tuple(sources)


@dataclass(frozen=True, slots=True)
class ComposedChangeAccess:
    """What the change capability asks, wired to this deployment's sources.

    The resource lookup is on this side of the seam deliberately: resolving
    "which resource is this" needs the estate and a tenant scope, and the
    capability layer is not allowed either. A resource the estate does not hold
    answers ``None``, which the tool reports as an alert naming something nobody
    is watching — a different finding from "nothing changed".
    """

    estate: EstateService
    scope: TenantScope
    sources: Sequence[Any]

    async def changes_for(self, resource: str, *, window: ChangeWindow) -> ChangeAnswer | None:
        """Return what changed for ``resource`` in ``window``, or ``None``."""
        detail = await self.estate.detail(self.scope, resource, now=window.end)
        if detail is None:
            return None
        view = views_of([detail.view.resource])[0]
        return await ChangeInquiry(sources=list(self.sources)).about(view, window=window)


async def compose_change_sources(state: GatewayState, *, org_id: str) -> tuple[Any, ...]:
    """Put this deployment's configured change sources on ``state`` and bind the tool.

    Returns what was composed, so a caller can log it. Binds the capability only
    when something was composed: an unbound tool reports that no change source
    is configured, and that is the answer an operator can act on — a bound tool
    over an empty source list would report "nothing changed" instead.
    """
    scope = TenantScope(org_id=org_id)
    config = ConfigService(gateway=state.gateway, scope=scope)
    try:
        effective = await config.resolve(org_id)
        sources = change_sources_from(effective.config.policies.changes)
    except UnsupportedGitHost as refused:
        logger.warning("changes.source_misconfigured", reason=str(refused))
        sources = ()
    except Exception as unreadable:  # noqa: BLE001 — an optional source must not stop a boot
        logger.warning("changes.source_unreadable", error=str(unreadable))
        sources = ()

    state.change_sources = sources
    binding.bind(
        None
        if not sources
        else ComposedChangeAccess(
            estate=EstateService(gateway=state.gateway, kinds=state.estate_kinds),
            scope=scope,
            sources=sources,
        )
    )
    logger.info("changes.sources_composed", sources=[type(each).__name__ for each in sources])
    return sources


__all__ = ["ComposedChangeAccess", "change_sources_from", "compose_change_sources"]

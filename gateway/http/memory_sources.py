"""Composing episodic memory per investigation: the search, and what fills it.

``recall_similar_incidents`` has reported "memory is not configured" on every
investigation this deployment has ever run, because nothing bound it a source.
The corpus behind it is empty for the matching reason: no serving path installed
the hook that turns a finished run into an episode, so there are no episodes, no
vector index and no generation to search.

**Both halves, or neither.** Binding the search on its own would trade an honest
unavailability for a confident wrong answer: an investigation would conclude "no
similar incidents" from a store nobody has ever written to, which is precisely
the failure the capability's unavailability path exists to prevent. So what this
composes is one ``MemoryService`` per run — the retriever the capability reads
and the finalisation hook that records the run — and a deployment that can
compose neither binds nothing and says so in a line.

**Per run, and scoped to the run's own team.** A retriever refuses a scope with
no team on it, because a search without one can return another team's incidents;
a lifecycle refuses one for the mirror reason, since an episode written without a
team is an episode every team retrieves. The team is on the request, so the
service is built when the run starts and not at boot — which is also what makes
the two investigations this deployment starts within milliseconds of each other
read their own corpora rather than whichever was composed last.

**The team's policy decides what exists at all.** Reading and writing switch
separately, and both off means *nothing composed*: the capability stays unbound
and reports an unavailability, rather than being offered and answering "nothing
found" about a corpus it was never allowed to open.

The embedder is ``LocalEmbedder``, which is the default the whole package is
designed around and the one the knowledge ingestor already composes: it reaches
no network, so a deployment whose operator may not send production text off their
own infrastructure still has an agent that can remember. It is lexical rather
than semantic, and a deployment that wants semantic recall installs a provider
behind the same port and re-embeds — which is a re-embedding generation rather
than something this composition root should decide per run.
"""

from __future__ import annotations

from config.constants.config_service import MODEL_ROLE_EXTRACTION
from core.llm import get_llm
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.runtime.investigator import RunMemory, RunMemoryFactory
from platform.config_service.bindings import memory_policy, strategy_policy
from platform.config_service.service import ConfigService
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.service import MemoryService
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope

logger = get_logger(__name__)


def compose_memory(state: GatewayState, *, org_id: str) -> bool:
    """Give the runner what to build each investigation's memory with, and say whether it took.

    ``False`` for a deployment whose runner takes no sources — the stand-in a
    process with no investigation runtime composed keeps running, and reporting
    that nothing was attached is more use than pretending something was.

    Called after the runner has been rebuilt from the published configuration.
    Attaching to a runner that is then replaced leaves the loop that actually
    runs with no memory at all, which is the state this closes.
    """
    attach = getattr(state.investigator, "attach_sources", None)
    if attach is None:
        logger.info("memory.sources_skipped", reason="this deployment composed no runner")
        return False

    attach(memory=memory_for(state, org_id=org_id))
    logger.info("memory.sources_composed", org=org_id)
    return True


def memory_for(state: GatewayState, *, org_id: str) -> RunMemoryFactory:
    """Return how this deployment builds one investigation's memory."""

    async def compose(request: InvestigationStart) -> RunMemory | None:
        team = request.team_node_id.strip()
        if not team:
            # An unscoped episode is one every team can retrieve and an unscoped
            # search is one that returns another team's incidents. Neither is
            # worth having, so a run with no team gets neither.
            logger.info("memory.run_unscoped", run_id=request.run_id)
            return None

        scope = TenantScope(org_id=org_id or request.org_id, team_node_id=team)
        try:
            effective = await ConfigService(gateway=state.gateway, scope=scope).resolve(team)
            policy = memory_policy(effective.config.policies)
            if not policy.enabled:
                logger.info("memory.switched_off", team=team, run_id=request.run_id)
                return None
            service = MemoryService(
                gateway=state.gateway,
                scope=scope,
                llm=get_llm(MODEL_ROLE_EXTRACTION),
                embedder=LocalEmbedder(),
                policy=policy,
                strategy_policy=strategy_policy(effective.config.policies),
                engine=state.guardrails,
            )
        except Exception as unreadable:  # noqa: BLE001 — memory must never fail a run
            # A policy that could not be read is not permission to read the
            # corpus, and a run this composition raised into is a run the
            # deployment lost to bookkeeping. Both come back as nothing
            # composed, with the reason recorded.
            logger.warning(
                "memory.not_composed", team=team, run_id=request.run_id, error=str(unreadable)
            )
            return None

        logger.info(
            "memory.composed",
            team=team,
            run_id=request.run_id,
            read=policy.read_enabled,
            write=policy.write_enabled,
            embedding_model=service.retriever.embedder.model,
        )
        return RunMemory(
            # Bound only when this team may read, so a team that writes without
            # reading is not offered a capability every call to which would come
            # back an unavailability — a wasted slot in a small budget.
            recall=service.recall if policy.read_enabled else None,
            hooks=service.install,
        )

    return compose


__all__ = ["compose_memory", "memory_for"]

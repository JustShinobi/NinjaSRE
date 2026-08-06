"""One history over every investigation, however it was started.

A scheduled run and an interactive one differ in their trigger and in their
principal. They differ in nothing else — same records, same trace, same episode,
same report — and this module is where that stops being a claim and becomes the
reason there is no second listing endpoint for "scheduled runs". A console that
had two lists would make "what has this team been doing" a question you answer
twice and then reconcile.

Filtering by team is a metadata read rather than a column, because the store's
run row is deliberately narrow and the team is one of several attributions the
recorder writes into it. That costs a scan the database could have indexed, and
it buys a port that does not gain a column every time the platform learns a new
way to attribute a run. The bound is the page size: this filters a page, it does
not walk a tenant.

Cost aggregation reads the turns, not the run. A run has no cost of its own —
what it cost is what its turns cost — and storing a total on the run would be a
second copy to keep in step with the records it was derived from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.runs import (
    DEFAULT_RUN_HISTORY_PAGE_SIZE,
    RUN_METADATA_JOB,
    RUN_METADATA_PARENT,
    RUN_METADATA_SUBAGENT,
    RUN_METADATA_TEAM,
    TURN_USAGE_COMPLETION_TOKENS,
    TURN_USAGE_COST,
    TURN_USAGE_PROMPT_TOKENS,
)
from core.agent.interaction.attention import (
    RUN_ATTENTION_KEY,
    RUN_ATTENTION_SINCE_KEY,
    Attention,
)
from core.agent.interaction.models import AttentionState
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, RunTraceStore
from platform.runs.events import TraceEventKind


@dataclass(frozen=True, slots=True)
class RunQuery:
    """What an operator is asking the history for.

    ``include_subagents`` defaults to false because a sub-agent run is part of
    its parent's investigation rather than a second one, and a list that showed
    both would report a team as having run three investigations when it ran one.
    """

    team_node_id: str | None = None
    status: RunStatus | None = None
    trigger: str | None = None
    job_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    include_subagents: bool = False
    limit: int = DEFAULT_RUN_HISTORY_PAGE_SIZE

    def matches(self, run: AgentRun) -> bool:
        """Return whether ``run`` satisfies the filters this query carries."""
        metadata = run.metadata
        if not self.include_subagents and bool(metadata.get(RUN_METADATA_SUBAGENT)):
            return False
        if self.team_node_id is not None and metadata.get(RUN_METADATA_TEAM) != self.team_node_id:
            return False
        if self.job_id is not None and metadata.get(RUN_METADATA_JOB) != self.job_id:
            return False
        return not (self.trigger is not None and run.trigger != self.trigger)


#: Sorts last a run whose metadata says it is waiting but not since when. It has
#: not waited longer than anybody; the writer simply did not say, and putting it
#: at the head of a queue ordered by how long people have been ignored would put
#: it in front of runs that actually have been.
_NEVER = datetime.max.replace(tzinfo=UTC)


def attention_from(recorded: Mapping[str, Any]) -> Attention:
    """Return the attention state a metadata map or an event payload describes."""
    state = str(recorded.get(RUN_ATTENTION_KEY, "") or "")
    if not state:
        return Attention()
    try:
        resolved = AttentionState(state)
    except ValueError:
        # A value nothing recognises means the writer and the reader disagree
        # about the vocabulary. Reporting "nothing needed" is the safe direction
        # to be wrong in for a filter, and the run still appears in an
        # unfiltered listing.
        return Attention()

    since = str(recorded.get(RUN_ATTENTION_SINCE_KEY, "") or "")
    return Attention(
        state=resolved,
        questions=int(recorded.get("questions", 0) or 0),
        approvals=int(recorded.get("approvals", 0) or 0),
        waiting_since=datetime.fromisoformat(since) if since else None,
        summary=str(recorded.get("summary", "") or ""),
    )


@dataclass(frozen=True, slots=True)
class CostSummary:
    """What a set of runs consumed.

    ``unpriced_runs`` is reported rather than folded into the total. A model
    whose pricing the deployment does not hold contributes tokens and no cost,
    and a total that quietly omitted them would understate a bill in a way
    nothing in the number itself reveals.
    """

    runs: int = 0
    turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    unpriced_runs: int = 0

    @property
    def total_tokens(self) -> int:
        """Return prompt and completion tokens together."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class RunHistory:
    """Reads over one tenant's runs, for a console or a report."""

    store: RunTraceStore

    async def list_runs(self, query: RunQuery | None = None) -> tuple[AgentRun, ...]:
        """Return the runs matching ``query``, most recently started first."""
        asked = query or RunQuery()
        page = await self.store.list_runs(
            status=asked.status,
            since=asked.since,
            until=asked.until,
            limit=asked.limit,
        )
        return tuple(run for run in page if asked.matches(run))

    async def attention_of(self, run_id: str) -> Attention:
        """Return what ``run_id`` is currently waiting on, from its own log.

        The latest ``attention_changed`` event wins. A run blocks and unblocks
        several times, and the run row is written once at the start and once at
        the end — so the log is the only place the intermediate states exist.
        A run that has finished needs nobody, whatever its last event said.
        """
        run = await self.store.get_run(run_id)
        if run is None or run.status is not RunStatus.RUNNING:
            return Attention()

        latest = Attention()
        cursor: int | None = None
        while True:
            page = await self.store.events_for_run(
                run_id, after=cursor, limit=DEFAULT_RUN_HISTORY_PAGE_SIZE
            )
            if not page:
                return latest
            for event in page:
                if event.kind == TraceEventKind.ATTENTION_CHANGED.value:
                    latest = attention_from(event.payload)
            cursor = page[-1].sequence

    async def awaiting_a_human(
        self, query: RunQuery | None = None
    ) -> tuple[tuple[AgentRun, Attention], ...]:
        """Return the runs that have stopped for somebody, longest-waiting first.

        Each run comes back with why it is waiting rather than only that it is.
        A console listing twenty investigations is read to decide where to spend
        the next twenty minutes, and "waiting on an approval since 11:12" is an
        answer to that where a flag is not.
        """
        asked = query or RunQuery()
        blocked: list[tuple[AgentRun, Attention]] = []
        for run in await self.list_runs(asked):
            attention = await self.attention_of(run.run_id)
            if attention.needs_attention:
                blocked.append((run, attention))
        return tuple(sorted(blocked, key=lambda pair: pair[1].waiting_since or _NEVER))

    async def children_of(
        self, run_id: str, *, limit: int = DEFAULT_RUN_HISTORY_PAGE_SIZE
    ) -> tuple[AgentRun, ...]:
        """Return the sub-agent runs dispatched by ``run_id``."""
        page = await self.store.list_runs(limit=limit)
        return tuple(run for run in page if run.metadata.get(RUN_METADATA_PARENT) == run_id)

    async def cost_of(self, run_id: str) -> CostSummary:
        """Return what one run consumed, added up from its turns."""
        return await self._aggregate((run_id,))

    async def cost_over(self, query: RunQuery | None = None) -> CostSummary:
        """Return what every run matching ``query`` consumed.

        Sub-agent runs are included when the query asks for them, and their cost
        is real cost either way — a report that excluded them would understate
        what an investigation with specialists actually spent.
        """
        runs = await self.list_runs(query)
        return await self._aggregate(tuple(run.run_id for run in runs))

    async def _aggregate(self, run_ids: Sequence[str]) -> CostSummary:
        """Return the summed usage of the named runs' turns."""
        tally = _Tally()
        for run_id in run_ids:
            tally.runs += 1
            priced = True
            for turn in await self.store.turns_for_run(run_id):
                usage = turn.usage
                tally.turns += 1
                tally.prompt_tokens += int(usage.get(TURN_USAGE_PROMPT_TOKENS, 0) or 0)
                tally.completion_tokens += int(usage.get(TURN_USAGE_COMPLETION_TOKENS, 0) or 0)
                cost = usage.get(TURN_USAGE_COST)
                if cost is None:
                    priced = False
                else:
                    tally.cost += float(cost)
            if not priced:
                tally.unpriced_runs += 1
        return tally.summary()


@dataclass(slots=True)
class _Tally:
    """The running total one aggregation accumulates."""

    runs: int = 0
    turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    unpriced_runs: int = 0

    def summary(self) -> CostSummary:
        """Return the immutable summary of what was counted."""
        return CostSummary(
            runs=self.runs,
            turns=self.turns,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cost=self.cost,
            unpriced_runs=self.unpriced_runs,
        )


__all__ = ["CostSummary", "RunHistory", "RunQuery", "attention_from"]

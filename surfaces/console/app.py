"""Routing, fetching, and the two rules that apply to every page.

The pages know nothing about HTTP and the client knows nothing about rendering.
This is where they meet, and it is deliberately the only place that does both —
so the two rules that must hold everywhere hold in one function rather than in
eleven.

**An unauthenticated visitor sees the sign-in and nothing else.** Checked before
routing, not inside each page, so a page added tomorrow is covered by having
been added (acceptance scenario 1).

**A 401 from any call ends the session.** Permissions can be revoked while the
console is open, and continuing to present a token the deployment has stopped
accepting is how a user gets a sequence of unexplained failures instead of one
clear "sign in again".

The renderer returns a ``Rendered`` rather than writing a response, because what
serves it is a deployment decision (feature 030) and because a test asserting
what a page contains should not have to stand up a server to find out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from surfaces.console.client import ConsoleApiError, ConsoleClient
from surfaces.console.html import Document, element
from surfaces.console.i18n import ENGLISH, Catalogue
from surfaces.console.pages import admin as admin_page
from surfaces.console.pages import auth as auth_page
from surfaces.console.pages import catalogue as catalogue_page
from surfaces.console.pages import config as config_page
from surfaces.console.pages import guardian as guardian_page
from surfaces.console.pages import interactions as interactions_page
from surfaces.console.pages import memory as memory_page
from surfaces.console.pages import runs as runs_page
from surfaces.console.pages.shell import PageContext, heading, page
from surfaces.console.permissions import Viewer
from surfaces.console.session import SIGN_IN_PATH, Session
from surfaces.console.transcript import TranscriptEvent
from surfaces.console.virtualisation import Window, window_at_end

#: Where a signed-in visitor lands. Runs, because that is what somebody opening
#: the console during an incident came for.
DEFAULT_PATH: Final = "/runs"

#: Statuses a page can end on that are not "here is the page".
STATUS_OK: Final = 200
STATUS_SEE_OTHER: Final = 303


@dataclass(frozen=True, slots=True)
class Rendered:
    """What answering one console request produced."""

    document: Document | None = None
    status: int = STATUS_OK
    location: str = ""
    #: The session as it stands afterwards. A caller writes it back to whatever
    #: it keeps sessions in; returning it rather than mutating one is what keeps
    #: this whole module a function of its arguments.
    session: Session = field(default_factory=Session)

    @property
    def is_redirect(self) -> bool:
        """Return whether this answer sends the visitor somewhere else."""
        return bool(self.location)

    def html(self) -> str:
        """Return the rendered page, or the empty string for a redirect."""
        return "" if self.document is None else self.document.render()


@dataclass(frozen=True, slots=True)
class Console:
    """The console as a whole: a client, a locale, and where the API lives."""

    client: ConsoleClient
    #: The API's origin as a browser would reach it. Used for the one form that
    #: must not post here — the credential form (SC-006).
    api_base: str = ""
    catalogue: Catalogue = ENGLISH

    async def render(
        self, path: str, session: Session, *, query: Mapping[str, str] | None = None
    ) -> Rendered:
        """Return the page at ``path`` for ``session``.

        Raises nothing a caller has to catch: an API failure becomes a page
        saying what went wrong, because a stack trace during an incident helps
        nobody who is looking at a browser.
        """
        if not session.is_usable():
            return self._sign_in(session.remembering(path), expired=session.is_authenticated)

        context = PageContext(
            viewer=session.viewer,
            path=path,
            catalogue=self.catalogue,
            notice=self.catalogue.text("auth.expiring") if session.is_expiring() else "",
        )
        client = self.client.with_token(session.token)

        try:
            return Rendered(
                document=await self._page(client, context, path, dict(query or {})),
                session=session.renewed(),
            )
        except ConsoleApiError as failure:
            if failure.is_unauthenticated:
                return self._sign_in(session.ended().remembering(path), expired=True)
            return Rendered(
                document=self._failure_page(context, failure), session=session.renewed()
            )

    def _sign_in(self, session: Session, *, expired: bool) -> Rendered:
        """Return the sign-in page, and nothing about the deployment behind it."""
        context = PageContext(
            viewer=Viewer(),
            path=SIGN_IN_PATH,
            catalogue=self.catalogue,
            notice=self.catalogue.text("auth.expired") if expired else "",
        )
        return Rendered(document=auth_page.sign_in_page(context), session=session)

    def _failure_page(self, context: PageContext, failure: ConsoleApiError) -> Document:
        """Return the page for an API refusal, in the three flavours that differ."""
        if failure.is_forbidden:
            message = context.text("common.forbidden")
        elif failure.is_missing:
            message = context.text("common.missing")
        else:
            message = context.text("common.unavailable")
        return page(
            context,
            title_key="app.name",
            body=element("div", heading(1, message), role="alert"),
        )

    async def _page(
        self,
        client: ConsoleClient,
        context: PageContext,
        path: str,
        query: Mapping[str, str],
    ) -> Document:
        """Return the document for one path, fetching whatever it needs."""
        if path.startswith("/runs/"):
            return await self._run_detail(client, context, path.removeprefix("/runs/"))
        if path.startswith("/config/") or path == "/config":
            return await self._config(client, context, path, query)
        if path.startswith("/memory/topology"):
            return await self._topology(client, context, query)
        if path.startswith("/memory"):
            return await self._memory(client, context, query)
        if path.startswith("/knowledge"):
            return await self._knowledge(client, context)
        if path.startswith("/interactions"):
            return await self._interactions(client, context)
        if path.startswith("/catalogue"):
            return await self._catalogue(client, context)
        if path.startswith("/guardian"):
            return await self._guardian(client, context)
        if path.startswith("/admin"):
            return await self._admin(client, context, query)
        if path.startswith("/onboarding"):
            return page(
                context,
                title_key="onboarding.title",
                body=admin_page.onboarding_body(context, admin_page.ONBOARDING_STEPS),
            )
        return await self._runs(client, context, query)

    # --- Areas ----------------------------------------------------------------

    async def _runs(
        self, client: ConsoleClient, context: PageContext, query: Mapping[str, str]
    ) -> Document:
        runs = await client.runs()
        return page(
            context,
            title_key="runs.title",
            body=runs_page.run_list_body(context, runs, selected=query),
        )

    async def _run_detail(
        self, client: ConsoleClient, context: PageContext, run_id: str
    ) -> Document:
        run = await client.run(run_id)
        replay = await client.replay(run_id)
        interactions = await client.interactions(run_id)
        events = transcript_events(replay)
        is_live = str(run.get("status", "")) in {"running", "waiting"}
        return page(
            context,
            title_key="runs.title",
            body=runs_page.run_detail_body(
                context,
                {**run, "cost": _cost_of(replay)},
                events,
                is_live=is_live,
                window=window_for(events),
                interactions=interactions,
            ),
        )

    async def _interactions(self, client: ConsoleClient, context: PageContext) -> Document:
        approvals = await client.approvals()
        waiting: list[Mapping[str, Any]] = [
            {
                "interaction_id": approval.get("approval_id", ""),
                "approval_id": approval.get("approval_id", ""),
                "run_id": approval.get("run_id", ""),
                "kind": interactions_page.APPROVAL_KIND,
                "text": approval.get("summary", ""),
                "is_open": approval.get("state") == "pending",
            }
            for approval in approvals
        ]
        return page(
            context,
            title_key="interactions.title",
            body=interactions_page.interaction_queue_body(context, waiting, approvals),
        )

    async def _memory(
        self, client: ConsoleClient, context: PageContext, query: Mapping[str, str]
    ) -> Document:
        component = query.get("component", "")
        return page(
            context,
            title_key="memory.title",
            body=memory_page.memory_body(
                context,
                await client.episodes(component=component),
                component=component,
                stats=await client.memory_stats(),
            ),
        )

    async def _topology(
        self, client: ConsoleClient, context: PageContext, query: Mapping[str, str]
    ) -> Document:
        service = query.get("service", "")
        topology = await client.topology(service) if service else {"node_id": "", "available": True}
        return page(
            context, title_key="memory.title", body=memory_page.topology_body(context, topology)
        )

    async def _knowledge(self, client: ConsoleClient, context: PageContext) -> Document:
        return page(
            context,
            title_key="knowledge.title",
            body=memory_page.knowledge_body(context, await client.documents()),
        )

    async def _config(
        self,
        client: ConsoleClient,
        context: PageContext,
        path: str,
        query: Mapping[str, str],
    ) -> Document:
        nodes = await client.config_tree()
        node_id = path.removeprefix("/config").strip("/")
        effective = await client.effective_config(node_id) if node_id else None
        preview = None
        if node_id and query.get("path"):
            preview = await client.preview_config(
                node_id, patch_of(query["path"], query.get("value", ""))
            )
        return page(
            context,
            title_key="config.title",
            body=config_page.config_body(
                context, nodes, node_id=node_id, effective=effective, preview=preview
            ),
        )

    async def _catalogue(self, client: ConsoleClient, context: PageContext) -> Document:
        node_id = context.viewer.team_node_id or ""
        catalogue = await client.catalogue(node_id) if node_id else {"entries": []}
        schemas = await client.integration_schemas(node_id) if node_id else ()
        return page(
            context,
            title_key="catalogue.title",
            body=catalogue_page.catalogue_body(
                context, catalogue, schemas=schemas, api_base=self.api_base
            ),
        )

    async def _guardian(self, client: ConsoleClient, context: PageContext) -> Document:
        """Return the shipped detector set as this deployment runs it.

        Fetched already resolved. The console could combine the shipped
        catalogue, the detected topology and the overrides itself — the
        arithmetic is not difficult — and the day its copy drifted from the
        server's, somebody would be shown a threshold the deployment does not
        use. That is the whole reason this page holds no rule of its own.
        """
        node_id = context.viewer.team_node_id or ""
        resolved = await client.guardian(node_id) if node_id else {}
        return page(
            context,
            title_key="guardian.title",
            body=guardian_page.guardian_body(context, resolved),
        )

    async def _admin(
        self, client: ConsoleClient, context: PageContext, query: Mapping[str, str]
    ) -> Document:
        return page(
            context,
            title_key="admin.title",
            body=admin_page.admin_body(
                context,
                people=await client.principals(),
                grants=await client.grants(),
                tokens=await client.tokens(),
                audit=await client.audit_events(**query),
            ),
        )


def transcript_events(replay: Mapping[str, Any]) -> tuple[TranscriptEvent, ...]:
    """Return a replay response as transcript events, in sequence order.

    Both shapes the API answers with are accepted — the raw event list a stream
    catch-up returns, and the turn list ``/replay`` returns — because the
    transcript component is the same either way and choosing between two
    components based on which endpoint answered is exactly the divergence
    FR-002 exists to prevent.
    """
    raw = replay.get("events")
    if isinstance(raw, list):
        return tuple(TranscriptEvent.of(record) for record in raw if isinstance(record, Mapping))
    turns = replay.get("turns")
    if not isinstance(turns, list):
        return ()
    return tuple(
        TranscriptEvent.of(
            {
                "run_id": replay.get("run_id", ""),
                "kind": "turn_completed",
                "sequence": index,
                "payload": turn,
            }
        )
        for index, turn in enumerate(turns)
        if isinstance(turn, Mapping)
    )


def window_for(events: Sequence[TranscriptEvent]) -> Window:
    """Return the window a run detail renders, anchored at the newest event."""
    return window_at_end(len(events))


def patch_of(path: str, value: str) -> dict[str, Any]:
    """Return the nested patch a dotted ``path`` and a ``value`` describe.

    Shape only — this expands ``a.b.c`` into three nested mappings and holds no
    opinion about what any of them mean. The merge, the locks, and the gating
    are all the server's (``POST /v1/config/{node}/preview``).
    """
    patch: dict[str, Any] = {}
    current = patch
    parts = [part for part in path.split(".") if part]
    for part in parts[:-1]:
        nested: dict[str, Any] = {}
        current[part] = nested
        current = nested
    if parts:
        current[parts[-1]] = value
    return patch


def _cost_of(replay: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the cost figures a replay carries."""
    return {
        "total_cost": replay.get("total_cost"),
        "total_tokens": replay.get("total_tokens"),
        "turns": len(replay.get("turns") or ()),
    }


__all__ = [
    "DEFAULT_PATH",
    "STATUS_OK",
    "STATUS_SEE_OTHER",
    "Console",
    "Rendered",
    "patch_of",
    "transcript_events",
    "window_for",
]

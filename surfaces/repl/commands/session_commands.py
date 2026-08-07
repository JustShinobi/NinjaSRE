"""``/sessions``, ``/resume``, ``/compact``, ``/new``, ``/exit``, and the four interaction ones.

Two groups that share a file because they share a fact: both act on the session
the loop is holding, and both do it by setting a field the loop reads rather
than by doing it themselves. A ``/exit`` that called ``sys.exit`` would take the
session's unsaved state with it; a ``/resume`` that swapped the object would
leave the loop holding the old one.

``/approve``, ``/answer``, ``/takeover``, and ``/cancel`` are here for the same
reason. They go through the interaction registry, which is where first-writer-
wins lives — a REPL that resolved a question locally and told the registry
afterwards would be a second surface racing the first with no arbiter.
"""

from __future__ import annotations

from config.constants.investigation import TRANSCRIPT_COMPACTION_KEEP_MESSAGES
from core.agent.interaction.models import InteractionKind
from surfaces.cli.errors import CliError, NotFoundError
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, table_of
from surfaces.repl.commands.registry import CommandContext, Registry, command
from surfaces.repl.interaction import APPROVAL_ANSWERS, only_one
from surfaces.repl.session import ReplSession

_SESSION_COLUMNS = (
    Column("Session id", weight=1),
    Column("Updated at", weight=2),
    Column("Turns", weight=1),
    Column("Evidence", weight=1),
    Column("Objective", weight=5),
)


def register_session_commands(registry: Registry) -> None:
    """Register the commands that manage a session and answer what it is waiting on."""

    @command(registry, "sessions", "List sessions you can pick up again.")
    def _sessions(context: CommandContext, arguments: str) -> None:
        if context.sessions is None:
            context.say("sessions are not being stored in this deployment")
            return
        found = context.sessions.list_sessions()
        context.say(
            table_of(
                records_of([session.summary() for session in found]),
                _SESSION_COLUMNS,
                terminal=context.terminal,
                empty="no earlier sessions",
            ).render(context.terminal)
        )

    @command(registry, "resume", "Pick up an earlier session.", usage="<session id>")
    def _resume(context: CommandContext, arguments: str) -> None:
        session_id = arguments.strip()
        if not session_id:
            raise CliError("which session?", remedy="see them with /sessions")
        if context.sessions is None:
            raise CliError("sessions are not being stored in this deployment")

        restored = context.sessions.load(session_id)
        if restored is None:
            raise NotFoundError(
                f"no session named {session_id!r}", remedy="see them with /sessions"
            )

        # Set for the loop rather than swapped here. The loop owns which session
        # is live, and two places deciding that is one place too many.
        context.switch_to = restored
        context.say(
            f"resumed {restored.session_id}: {len(restored.transcript)} exchanges, "
            f"{len(restored.evidence_ids)} pieces of evidence, "
            f"{restored.cost.total_tokens:,} tokens spent"
        )

    @command(
        registry,
        "compact",
        "Shorten the transcript, keeping every evidence reference.",
        usage="[keep]",
    )
    def _compact(context: CommandContext, arguments: str) -> None:
        keep = TRANSCRIPT_COMPACTION_KEEP_MESSAGES
        if arguments.strip():
            if not arguments.strip().isdigit():
                raise CliError(f"{arguments.strip()!r} is not a number of exchanges to keep")
            keep = int(arguments.strip())

        before = len(context.session.evidence_ids)
        dropped = context.session.compact(keep=keep)
        after = len(context.session.evidence_ids)
        context.say(
            f"dropped {dropped} exchanges, kept {after} evidence references"
            + (f" (was {before})" if after != before else "")
        )

    @command(registry, "new", "Start a fresh session.")
    def _new(context: CommandContext, arguments: str) -> None:
        if context.sessions is not None:
            context.sessions.save(context.session)
        context.switch_to = ReplSession(
            team_node_id=context.session.team_node_id,
            model_id=context.session.model_id,
            effort=context.session.effort,
        )
        context.say(f"new session {context.switch_to.session_id}")

    @command(registry, "exit", "Leave.", aliases=("quit",))
    def _exit(context: CommandContext, arguments: str) -> None:
        context.should_exit = True

    @command(registry, "cancel", "Stop the investigation at its next safe point.")
    def _cancel(context: CommandContext, arguments: str) -> None:
        if not context.session.active_run_id:
            context.say("nothing is running")
            return
        # A request rather than a kill. The runtime knows where stopping is
        # safe; a signal does not, and a run stopped mid-tool-call leaves its
        # evidence half-written and its record saying "running" forever.
        context.cancel_requested = True
        context.say(f"asked {context.session.active_run_id} to stop at its next safe point")

    @command(registry, "approve", "Resolve a pending approval.", usage="[id] approve|decline")
    def _approve(context: CommandContext, arguments: str) -> None:
        if context.interactions is None:
            context.say("this session is not attached to a run")
            return

        parts = arguments.split()
        pending = context.interactions.pending(InteractionKind.APPROVAL)
        if not parts:
            context.interactions.show_pending(InteractionKind.APPROVAL)
            return

        if len(parts) == 1:
            # One word. It has to be the decision, and there has to be exactly
            # one thing waiting — guessing which of two production changes
            # somebody meant is not a convenience.
            single = only_one(pending)
            if single is None:
                raise CliError(
                    f"{len(pending)} approvals are pending",
                    remedy="name the one you mean: /approve <id> approve|decline",
                )
            interaction_id, decision = single.interaction_id, parts[0]
        else:
            interaction_id, decision = parts[0], parts[1]

        try:
            context.interactions.approve(interaction_id, decision)
        except ValueError as refused:
            raise CliError(str(refused), remedy=f"say {' or '.join(APPROVAL_ANSWERS)}") from refused

    @command(registry, "answer", "Answer a pending question.", usage="[id] <your answer>")
    def _answer(context: CommandContext, arguments: str) -> None:
        if context.interactions is None:
            context.say("this session is not attached to a run")
            return

        pending = context.interactions.pending(InteractionKind.QUESTION)
        if not arguments.strip():
            context.interactions.show_pending(InteractionKind.QUESTION)
            return

        head, _, rest = arguments.strip().partition(" ")
        known = {interaction.interaction_id for interaction in pending}
        if head in known:
            interaction_id, text = head, rest.strip()
        else:
            single = only_one(pending)
            if single is None:
                raise CliError(
                    f"{len(pending)} questions are pending",
                    remedy="name the one you mean: /answer <id> <your answer>",
                )
            interaction_id, text = single.interaction_id, arguments.strip()

        if not text:
            raise CliError("an answer with no text is not an answer")
        context.interactions.answer(interaction_id, text)

    @command(registry, "takeover", "Take control: pause the agent and close what it asked.")
    def _takeover(context: CommandContext, arguments: str) -> None:
        if context.interactions is None:
            context.say("this session is not attached to a run")
            return
        closed = context.interactions.takeover(arguments.strip())
        context.cancel_requested = bool(context.session.active_run_id)
        context.say(
            f"you have control. {len(closed)} open interaction(s) closed"
            + ("; the run will stop at its next safe point" if context.cancel_requested else "")
        )


__all__ = ["register_session_commands"]

"""``/status``, ``/cost``, ``/runs``, ``/integrations``, ``/effort``, ``/model``.

The commands that report what is going on and adjust bounded parameters. Every
one is a read of state the session or the platform already holds, which is what
lets them run with no model call.

``/effort`` and ``/model`` change parameters within bounds; the bounds
themselves stay named constants. A session that could raise its own ceiling
would make Article II's ceilings advisory, so what these do is choose inside a
range rather than move the range.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from config.constants.investigation import REASONING_EFFORT_LEVELS
from config.constants.llm import SUPPORTED_PROVIDERS
from surfaces.cli.errors import CliError
from surfaces.cli.models import records_of
from surfaces.cli.output.tables import Column, Detail, table_of
from surfaces.repl.commands.registry import CommandContext, Registry, command


def _await[Result](work: Coroutine[Any, Any, Result]) -> Result:
    """Run one coroutine to completion from inside a synchronous handler.

    Slash-command handlers are synchronous on purpose — see the registry — but
    the platform client is async because everything below it is. One loop per
    call is the honest cost of that, and it is a read against a store rather
    than an investigation.
    """
    return asyncio.run(work)


def register_state_commands(registry: Registry) -> None:
    """Register the commands that report or adjust session state."""

    @command(registry, "status", "What this session is doing right now.")
    def _status(context: CommandContext, arguments: str) -> None:
        session = context.session
        pairs = [
            ("Session", session.session_id),
            ("Objective", session.objective or "nothing yet"),
            ("Team", session.team_node_id or "default"),
            ("Model", session.model_id or "as configured"),
            ("Effort", session.effort or "as configured"),
            ("Exchanges", str(len(session.transcript))),
            ("Evidence", str(len(session.evidence_ids))),
            ("Active run", session.active_run_id or "none"),
            ("Waiting on you", ", ".join(session.awaiting) or "nothing"),
        ]
        context.say(Detail(title="Status", pairs=tuple(pairs)).render(context.terminal))

    @command(registry, "cost", "Token usage and cost, for this session and its runs.")
    def _cost(context: CommandContext, arguments: str) -> None:
        session = context.session
        cost = session.cost
        pairs = [
            ("Runs", str(cost.runs)),
            ("Turns", str(cost.turns)),
            ("Prompt tokens", f"{cost.prompt_tokens:,}"),
            ("Completion tokens", f"{cost.completion_tokens:,}"),
            ("Total tokens", f"{cost.total_tokens:,}"),
            ("Cost", f"{cost.cost:.4f}"),
        ]
        if cost.unpriced_runs:
            # Reported rather than folded in: a model whose pricing this
            # deployment does not hold contributes tokens and no cost, and a
            # total that hid that understates a bill invisibly.
            pairs.append(("Runs with no pricing", str(cost.unpriced_runs)))
        context.say(
            Detail(title=f"Cost for session {session.session_id}", pairs=tuple(pairs)).render(
                context.terminal
            )
        )

        if context.client is not None and session.active_run_id:
            detail = _await(context.client.show_run(session.active_run_id))
            context.say(
                f"\nActive run {session.active_run_id}: "
                f"{detail.cost.total_tokens:,} tokens, {detail.cost.cost:.4f}"
            )

    @command(registry, "runs", "Recent investigations.", usage="[list|show <id>]")
    def _runs(context: CommandContext, arguments: str) -> None:
        if context.client is None:
            context.say("this session is not attached to a deployment")
            return

        action, _, rest = arguments.strip().partition(" ")
        if action == "show" and rest.strip():
            detail = _await(context.client.show_run(rest.strip()))
            context.say(
                Detail(
                    title=detail.run.run_id,
                    pairs=(
                        ("Status", detail.run.status),
                        ("Objective", detail.run.objective),
                        ("Evidence", str(len(detail.evidence_ids))),
                        ("Tokens", f"{detail.cost.total_tokens:,}"),
                    ),
                    sections=(("Result", detail.result),),
                ).render(context.terminal)
            )
            return

        runs = _await(context.client.list_runs(team_node_id=context.session.team_node_id, limit=10))
        context.say(
            table_of(
                records_of(runs),
                (
                    Column("Run id", weight=1),
                    Column("Status", weight=1),
                    Column("Objective", weight=5),
                ),
                terminal=context.terminal,
                empty="no runs yet",
            ).render(context.terminal)
        )

    @command(
        registry, "integrations", "Integration state and health.", usage="[list|verify <name>]"
    )
    def _integrations(context: CommandContext, arguments: str) -> None:
        if context.client is None:
            context.say("this session is not attached to a deployment")
            return

        action, _, rest = arguments.strip().partition(" ")
        if action == "verify" and rest.strip():
            status = _await(context.client.verify_integration(rest.strip()))
            glyph = context.terminal.glyph("ok" if status.healthy else "failed")
            context.say(f"{glyph} {status.integration}: {status.detail or status.credential_state}")
            return

        integrations = _await(context.client.list_integrations())
        context.say(
            table_of(
                records_of(integrations),
                (
                    Column("Integration", weight=2),
                    Column("Configured", weight=1),
                    Column("Healthy", weight=1),
                    Column("Detail", weight=4),
                ),
                terminal=context.terminal,
                empty="nothing is integrated",
            ).render(context.terminal)
        )

    @command(
        registry,
        "effort",
        "Reasoning effort for this session, where the provider supports it.",
        usage="<level>",
    )
    def _effort(context: CommandContext, arguments: str) -> None:
        level = arguments.strip().lower()
        if not level:
            context.say(
                f"effort is {context.session.effort or 'as configured'}; "
                f"one of: {', '.join(REASONING_EFFORT_LEVELS)}"
            )
            return
        if level not in REASONING_EFFORT_LEVELS:
            raise CliError(
                f"{level!r} is not an effort level",
                remedy=f"one of: {', '.join(REASONING_EFFORT_LEVELS)}",
            )
        context.session.effort = level
        context.say(f"effort for this session is now {level}")

    @command(registry, "model", "Switch the model for this session.", usage="<name>")
    def _model(context: CommandContext, arguments: str) -> None:
        name = arguments.strip()
        if not name:
            context.say(f"model is {context.session.model_id or 'as configured'}")
            if context.client is not None:
                configured = [
                    status
                    for status in _await(context.client.list_providers())
                    if status.configured
                ]
                if configured:
                    context.say(
                        "configured providers: "
                        + ", ".join(
                            f"{status.provider_id} ({status.model_id})" for status in configured
                        )
                    )
                else:
                    context.say(f"supported providers: {', '.join(SUPPORTED_PROVIDERS)}")
            return
        context.session.model_id = name
        context.say(f"model for this session is now {name}")


__all__ = ["register_state_commands"]

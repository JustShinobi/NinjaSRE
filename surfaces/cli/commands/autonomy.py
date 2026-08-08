"""``ninjasre autonomy`` — how much the deployment may do without asking.

Eight commands over one service, and ``why`` is the one that matters most. An
operator whose deployment did nothing at four in the morning has exactly one
question, and it is not "what is my configuration" — it is "why was *this*
refused". ``why`` answers it about a specific action against a specific
resource, from the same resolver the gate uses, so the answer is what the
deployment would actually do rather than a reading of the document.

Two shapes are worth explaining.

**A posture is exported and applied as one document.** ``show --json`` prints
what ``apply --file`` accepts, unchanged. A surface where the export had to be
translated before it could be applied is a surface where the translation is the
thing that goes wrong, silently, at the moment somebody is restoring a posture.

**Stopping does not take a node.** The kill switch is not a per-node setting and
is deliberately not part of the policy document: it is the control an operator
reaches for when they have neither the time nor the confidence to work out what
is currently permitted, and one that asked which node first would not be one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from config.constants.autonomy import (
    AUTONOMY_LEVELS,
    DEFAULT_AUTONOMY_OVERRIDE_SECONDS,
    RISK_CLASSES,
)
from surfaces.cli.errors import CliError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import AutonomyExplanation, AutonomyPolicyRecord
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(
    help="Autonomy: what may happen without a person, and what bounds it.",
    no_args_is_help=True,
)

#: How far back a preview reads when the operator does not say. A week, because
#: that is the window somebody has an intuition about.
DEFAULT_PREVIEW_DAYS = 7.0

_RULE_COLUMNS = (
    Column("Scope", weight=3),
    Column("Level", weight=2),
    Column("Up to risk", weight=2),
    Column("Simulated", weight=1),
)

_CONSIDERED_COLUMNS = (
    Column("Rule", weight=3),
    Column("Scope", weight=3),
    Column("Level", weight=2),
    Column("Applied", weight=1),
    Column("Won", weight=1),
)

_PREVIEW_COLUMNS = (
    Column("Capability", weight=2),
    Column("Resources", weight=3),
    Column("Was", weight=2),
    Column("Would be", weight=2),
)

_FREEZE_COLUMNS = (
    Column("Freeze", weight=2),
    Column("From", weight=1),
    Column("Until", weight=1),
    Column("Timezone", weight=2),
)

_BUDGET_COLUMNS = (
    Column("Budget", weight=2),
    Column("Counted by", weight=2),
    Column("Limit", weight=1),
    Column("Interval (s)", weight=2),
)


def _document_from(file: Path | None) -> dict[str, Any]:
    """Return the policy document at ``file``, refusing anything unreadable.

    Read from a file rather than from flags. A posture is a document somebody
    reviews, and a command line that could express one would be a second
    grammar for the most safety-critical setting in the system.
    """
    if file is None:
        raise CliError(
            "a policy document is required",
            remedy="pass --file with the document `ninjasre autonomy show --json` prints",
        )
    try:
        loaded = json.loads(file.read_text(encoding="utf-8"))
    except OSError as unreadable:
        raise CliError(f"could not read {file}: {unreadable}") from unreadable
    except json.JSONDecodeError as malformed:
        raise CliError(f"{file} is not JSON: {malformed}") from malformed
    if not isinstance(loaded, dict):
        raise CliError(f"{file} does not hold a policy document")
    # ``show --json`` wraps the document beside the rendering; accept either, so
    # an operator can pipe the export straight back in.
    document = loaded.get("document", loaded)
    if not isinstance(document, dict):
        raise CliError(f"{file} does not hold a policy document")
    return document


def _rule_rows(policy: AutonomyPolicyRecord) -> list[dict[str, object]]:
    """Return the rules a table renders, in the column order above."""
    return [
        {
            "scope": rule.scope,
            "level": rule.level,
            "risk_bound": rule.risk_bound if rule.level == "act_on_low_risk" else "—",
            "dry_run": "yes" if rule.dry_run else "no",
        }
        for rule in policy.rules
    ]


def _policy_text(policy: AutonomyPolicyRecord, invocation: Invocation) -> str:
    """Return the posture as an operator reads it, simulation said first."""
    table = table_of(
        _rule_rows(policy),
        _RULE_COLUMNS,
        terminal=invocation.terminal,
        empty="nothing is configured, so every action needs a person",
    ).render(invocation.terminal)
    if not policy.dry_run:
        return table
    return f"Everything here is simulated: dry-run is on for this node.\n\n{table}"


def _explanation_text(explained: AutonomyExplanation, invocation: Invocation) -> str:
    """Return the explanation as an operator reads it: the answer, then the working."""
    header = Detail(
        title=f"{explained.decision}: {explained.reason}",
        pairs=(
            ("Level", explained.level),
            ("Risk class", explained.risk_class),
            ("Risk bound", explained.risk_bound),
            ("Refused by", explained.refused_by or "nothing"),
            ("Winning rule", explained.winning_rule or "none — the default applies"),
            ("Simulated", "yes" if explained.dry_run else "no"),
            ("A person could run", explained.operation or "—"),
        ),
    ).render(invocation.terminal)
    considered = table_of(
        [
            {
                "rule_id": entry.rule_id,
                "scope": entry.scope,
                "level": entry.level,
                "applied": "yes" if entry.applied else "no",
                "won": "yes" if entry.won else "no",
            }
            for entry in explained.considered
        ],
        _CONSIDERED_COLUMNS,
        terminal=invocation.terminal,
        empty="no rule was configured, so nothing was considered",
    ).render(invocation.terminal)
    return f"{header}\n\n{considered}"


@app.command("show")
def show_policy(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
) -> None:
    """Show what this node may do without asking, inheritance applied."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        policy = await invocation.client().autonomy_policy(node_id)
        return Output(
            command="autonomy.show",
            data=policy.to_record(),
            text=_policy_text(policy, invocation),
        )

    raise typer.Exit(run_command(invocation, "autonomy.show", body))


@app.command("why")
def why(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
    capability: str = typer.Option(..., "--capability", help="Which action."),
    resource: list[str] = typer.Option(
        ..., "--resource", help="Which resource it would change. Repeatable."
    ),
    kind: str = typer.Option("", "--kind", help="The resource's kind, for a kind-scoped rule."),
    label: list[str] = typer.Option(
        [], "--label", help="A label as name=value, for a label-scoped rule. Repeatable."
    ),
    risk: str = typer.Option(
        "", "--risk", help=f"The action's risk class: {', '.join(RISK_CLASSES)}."
    ),
    no_rollback: bool = typer.Option(
        False, "--no-rollback", help="Ask as though the action had no rollback plan."
    ),
) -> None:
    """Explain what would happen to one action, and every reason it would.

    Nothing is performed. This resolves a hypothetical through the same resolver
    the gate uses, so the answer is what the deployment would do rather than a
    reading of the configuration.
    """
    invocation: Invocation = ctx.obj
    labels: dict[str, str] = {}
    for entry in label:
        name, separator, value = entry.partition("=")
        if not separator or not name:
            raise CliError(f"{entry!r} is not a label", remedy="write labels as name=value")
        labels[name] = value

    async def body() -> Output:
        explained = await invocation.client().explain_autonomy(
            node_id,
            {
                "capability": capability,
                "subjects": [
                    {"resource_id": identifier, "kind": kind, "labels": labels}
                    for identifier in resource
                ],
                "risk_class": risk,
                "has_rollback_plan": not no_rollback,
            },
        )
        return Output(
            command="autonomy.why",
            data=explained.to_record(),
            text=_explanation_text(explained, invocation),
        )

    raise typer.Exit(run_command(invocation, "autonomy.why", body))


@app.command("bounds")
def bounds(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
) -> None:
    """Show the freeze windows, budgets, overrides and stop bounding this node."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().autonomy_bounds(node_id)
        freezes = table_of(
            [
                {
                    "name": str(entry.get("name", "")),
                    "start": str(entry.get("start", "")),
                    "end": str(entry.get("end", "")),
                    "timezone": str(entry.get("timezone", "")),
                }
                for entry in found.freezes
            ],
            _FREEZE_COLUMNS,
            terminal=invocation.terminal,
            empty="no freeze windows",
        ).render(invocation.terminal)
        budgets = table_of(
            [
                {
                    "name": str(entry.get("name", "")),
                    "counted_by": str(entry.get("counted_by", "")),
                    "limit": str(entry.get("limit", "")),
                    "interval_seconds": str(entry.get("interval_seconds", "")),
                }
                for entry in found.budgets
            ],
            _BUDGET_COLUMNS,
            terminal=invocation.terminal,
            empty="no budgets",
        ).render(invocation.terminal)
        stopped = f"Automated writes are stopped: {found.stop_reason}\n\n" if found.stopped else ""
        return Output(
            command="autonomy.bounds",
            data=found.to_record(),
            text=f"{stopped}{freezes}\n\n{budgets}",
        )

    raise typer.Exit(run_command(invocation, "autonomy.bounds", body))


@app.command("preview")
def preview(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
    file: Path = typer.Option(None, "--file", help="The proposed policy document."),
    days: float = typer.Option(DEFAULT_PREVIEW_DAYS, "--days", help="How far back to replay."),
) -> None:
    """Show what this change would have decided differently, and change nothing."""
    invocation: Invocation = ctx.obj
    document = _document_from(file)

    async def body() -> Output:
        change = await invocation.client().preview_autonomy_policy(node_id, document, days=days)
        rows = table_of(
            [
                {
                    "capability": entry.capability,
                    "subjects": ", ".join(entry.subjects),
                    "before": entry.before,
                    "after": entry.after,
                }
                for entry in change.actions
                if entry.changed
            ],
            _PREVIEW_COLUMNS,
            terminal=invocation.terminal,
            empty="nothing recorded would have been decided differently",
        ).render(invocation.terminal)
        return Output(
            command="autonomy.preview",
            data=change.to_record(),
            text=f"{change.summary}\n\n{rows}",
        )

    raise typer.Exit(run_command(invocation, "autonomy.preview", body))


@app.command("apply")
def apply_policy(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
    file: Path = typer.Option(None, "--file", help="The policy document to apply."),
) -> None:
    """Replace this node's posture with the document in ``--file``."""
    invocation: Invocation = ctx.obj
    document = _document_from(file)

    async def body() -> Output:
        policy = await invocation.client().apply_autonomy_policy(node_id, document)
        return Output(
            command="autonomy.apply",
            data=policy.to_record(),
            text=_policy_text(policy, invocation),
        )

    raise typer.Exit(run_command(invocation, "autonomy.apply", body))


@app.command("dry-run")
def set_dry_run(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
    off: bool = typer.Option(False, "--off", help="Turn simulation off again."),
) -> None:
    """Simulate everything this node resolves, executing nothing."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        policy = await invocation.client().set_autonomy_dry_run(node_id, enabled=not off)
        return Output(
            command="autonomy.dry-run",
            data=policy.to_record(),
            text=_policy_text(policy, invocation),
        )

    raise typer.Exit(run_command(invocation, "autonomy.dry-run", body))


@app.command("override")
def grant_override(
    ctx: typer.Context,
    node_id: str = typer.Argument(..., help="Which configuration node."),
    name: str = typer.Option(..., "--name", help="What this override is called."),
    level: str = typer.Option(
        ..., "--level", help=f"The level to raise to: {', '.join(AUTONOMY_LEVELS)}."
    ),
    reason: str = typer.Option(..., "--reason", help="Why. Required, and recorded."),
    hours: float = typer.Option(
        DEFAULT_AUTONOMY_OVERRIDE_SECONDS / 3600,
        "--hours",
        help="How long it lasts before it expires by itself.",
    ),
) -> None:
    """Raise autonomy for a while, expiring by itself and audibly."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        granted = await invocation.client().grant_autonomy_override(
            node_id,
            {
                "name": name,
                "level": level,
                "reason": reason,
                "seconds": hours * 3600,
            },
        )
        return Output(
            command="autonomy.override",
            data=granted.to_record(),
            text=(
                f"{granted.name} raises this node to {granted.level} until "
                f"{granted.expires_at.isoformat() if granted.expires_at else 'unknown'}, "
                f"granted by {granted.granted_by or 'you'}."
            ),
        )

    raise typer.Exit(run_command(invocation, "autonomy.override", body))


@app.command("stop")
def stop(
    ctx: typer.Context,
    reason: str = typer.Option(..., "--reason", help="Why. Required, and recorded."),
    scope: str = typer.Option("", "--scope", help="One team, rather than everything."),
) -> None:
    """Stop every automated write, immediately, whatever any policy says."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        switch = await invocation.client().engage_kill_switch(reason=reason, scope=scope)
        return Output(
            command="autonomy.stop",
            data=switch.to_record(),
            text=(
                "Automated writes are stopped. Nothing runs unattended until this is "
                "released, whatever any policy says."
            ),
        )

    raise typer.Exit(run_command(invocation, "autonomy.stop", body))


@app.command("resume")
def resume(
    ctx: typer.Context,
    scope: str = typer.Option("", "--scope", help="One team, rather than everything."),
) -> None:
    """Let automated writes happen again, attributed to whoever asked."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        switch = await invocation.client().release_kill_switch(scope=scope)
        remaining = ", ".join(sorted(switch.scopes)) or "none"
        return Output(
            command="autonomy.resume",
            data=switch.to_record(),
            text=f"Released. Scopes still stopped: {remaining}.",
        )

    raise typer.Exit(run_command(invocation, "autonomy.resume", body))


__all__ = ["app"]

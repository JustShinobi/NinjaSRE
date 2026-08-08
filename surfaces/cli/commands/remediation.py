"""``ninjasre remediation`` — what was changed, whether it worked, and what to do.

Four listings and two writes, over the ledger of what the deployment has
actually done to production. Two shapes are worth explaining.

**"Awaiting verification" is a state, printed as one.** A row for an action
whose settle period has not elapsed says so in the state column rather than
leaving the verdict blank, because a blank cell reads as "fine" to somebody
scanning a table at three in the morning.

**Both writes require the sentence that justifies them.** ``--reason`` on a
clear and ``--change`` on a close are required by the command rather than
prompted for, so a script has to supply one too. A suspension cleared with no
reason records that nobody looked, and a recurring problem closed with no change
records that it stopped being displayed.
"""

from __future__ import annotations

import typer

from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import RemediationOutcomeRecord, records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(
    help="Remediation: what was changed, and whether it worked.",
    no_args_is_help=True,
)

_OUTCOME_COLUMNS = (
    Column("Action id", weight=3),
    Column("Capability", weight=2),
    Column("Resource", weight=2),
    Column("State", weight=2),
    Column("Signals", weight=4),
    Column("Executed at", weight=2),
)

_PROBLEM_COLUMNS = (
    Column("Problem id", weight=3),
    Column("Capability", weight=2),
    Column("Resource", weight=2),
    Column("Times", weight=1),
    Column("Suppressing", weight=1),
    Column("Raised at", weight=2),
)

_SUSPENSION_COLUMNS = (
    Column("Resource", weight=2),
    Column("Since", weight=2),
    Column("Why", weight=5),
    Column("Live", weight=1),
)


def _outcome_rows(outcomes: tuple[RemediationOutcomeRecord, ...]) -> list[dict[str, object]]:
    """Return the records a table renders, in the column order above."""
    return [
        {
            "action_id": record.action_id,
            "capability": record.capability,
            "resource_id": record.resource_id,
            "state": record.state,
            "signals": record.movement(),
            "executed_at": record.executed_at,
        }
        for record in outcomes
    ]


@app.command("list")
def list_remediations(
    ctx: typer.Context,
    resource: str = typer.Option("", "--resource", help="Only actions against this resource."),
    capability: str = typer.Option("", "--capability", help="Only this capability's actions."),
    condition: str = typer.Option("", "--condition", help="Only actions against this condition."),
    limit: int = typer.Option(25, "--limit", help="How many to return."),
) -> None:
    """List what the deployment has changed, most recent first."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_remediations(
            resource=resource, capability=capability, condition=condition, limit=limit
        )
        awaiting = len([record for record in found if record.awaiting_verification])
        table = table_of(
            _outcome_rows(found),
            _OUTCOME_COLUMNS,
            terminal=invocation.terminal,
            empty="this deployment has not changed anything",
        ).render(invocation.terminal)
        note = (
            f"\n\n{awaiting} of these are still settling and nothing is known about "
            f"whether they worked."
            if awaiting
            else ""
        )
        return Output(
            command="remediation.list",
            data={"outcomes": records_of(found), "awaiting": awaiting},
            text=f"{table}{note}",
        )

    raise typer.Exit(run_command(invocation, "remediation.list", body))


@app.command("effectiveness")
def effectiveness(
    ctx: typer.Context,
    capability: str = typer.Option("", "--capability", help="Which capability."),
    resource: str = typer.Option("", "--resource", help="Which resource."),
    condition: str = typer.Option("", "--condition", help="Which condition it was taken against."),
) -> None:
    """Say how often this has worked, and whether it argues against trying again."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        record = await invocation.client().remediation_effectiveness(
            capability=capability, resource=resource, condition=condition
        )
        counts = ", ".join(f"{name} {count}" for name, count in sorted(record.counts.items()))
        detail = Detail(
            title=record.summary or "nothing has been tried here",
            pairs=(
                ("Actions", str(record.total)),
                ("Verified", str(record.verified)),
                ("Still settling", str(record.awaiting)),
                ("Worked", f"{record.success_ratio:.0%}" if record.known else "not known yet"),
                ("Verdicts", counts or "none yet"),
                ("Last verdict", record.last_verdict or "none yet"),
            ),
        ).render(invocation.terminal)
        return Output(
            command="remediation.effectiveness",
            data=record.to_record(),
            text=detail,
        )

    raise typer.Exit(run_command(invocation, "remediation.effectiveness", body))


@app.command("problems")
def list_problems(
    ctx: typer.Context,
    all_problems: bool = typer.Option(
        False, "--all", help="Include the patterns somebody has already closed."
    ),
) -> None:
    """List the recurring problems: patterns, closed by a change rather than a fix."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_recurring_problems(live_only=not all_problems)
        table = table_of(
            [
                {
                    "problem_id": record.problem_id,
                    "capability": record.capability,
                    "resource_id": record.resource_id,
                    "occurrences": str(record.occurrences),
                    "suppressing": "yes" if record.live and record.suppresses_autonomy else "no",
                    "raised_at": record.raised_at,
                }
                for record in found
            ],
            _PROBLEM_COLUMNS,
            terminal=invocation.terminal,
            empty="nothing has happened often enough to be a pattern",
        ).render(invocation.terminal)
        return Output(
            command="remediation.problems",
            data={"problems": records_of(found)},
            text=table,
        )

    raise typer.Exit(run_command(invocation, "remediation.problems", body))


@app.command("close-problem")
def close_problem(
    ctx: typer.Context,
    problem_id: str = typer.Argument(..., help="Which recurring problem."),
    change: str = typer.Option(
        ..., "--change", help="The change that closed it. Required — a fix is not a change."
    ),
) -> None:
    """Close a recurring problem, naming the change, and lift its suppression."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        closed = await invocation.client().close_recurring_problem(problem_id, change=change)
        return Output(
            command="remediation.close-problem",
            data=closed.to_record(),
            text=(
                f"{closed.problem_id} is closed: {closed.close_reason}. "
                f"{closed.capability} on {closed.resource_id} may run unattended again."
            ),
        )

    raise typer.Exit(run_command(invocation, "remediation.close-problem", body))


@app.command("suspensions")
def list_suspensions(
    ctx: typer.Context,
    all_suspensions: bool = typer.Option(
        False, "--all", help="Include the suspensions somebody has already cleared."
    ),
) -> None:
    """List the resources this deployment has stopped acting on unattended."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_suspensions(live_only=not all_suspensions)
        table = table_of(
            [
                {
                    "resource_id": record.resource_id,
                    "since": record.since,
                    "reason": record.reason,
                    "live": "yes" if record.live else "no",
                }
                for record in found
            ],
            _SUSPENSION_COLUMNS,
            terminal=invocation.terminal,
            empty="autonomy is not suspended anywhere",
        ).render(invocation.terminal)
        return Output(
            command="remediation.suspensions",
            data={"suspensions": records_of(found)},
            text=table,
        )

    raise typer.Exit(run_command(invocation, "remediation.suspensions", body))


@app.command("clear-suspension")
def clear_suspension(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Which resource."),
    reason: str = typer.Option(..., "--reason", help="What you found when you looked. Required."),
) -> None:
    """Let autonomy resume on a resource, on the record."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        cleared = await invocation.client().clear_suspension(resource_id, reason=reason)
        return Output(
            command="remediation.clear-suspension",
            data=cleared.to_record(),
            text=(
                f"{cleared.resource_id} is no longer suspended: {cleared.clear_reason} "
                f"(cleared by {cleared.cleared_by or 'you'})."
            ),
        )

    raise typer.Exit(run_command(invocation, "remediation.clear-suspension", body))

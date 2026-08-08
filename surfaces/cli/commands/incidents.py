"""``ninjasre incidents`` and ``ninjasre detectors`` — what is wrong, and what is watching.

Two command groups over the same pair of services, because an operator asking
"why did nothing happen" moves between them: the incident list says a firing was
suppressed, and the detector list says what the detector was looking at.

Two shapes are worth explaining.

**A listing names every subject.** The table shows the first few and the count
of the rest; ``--json`` carries all of them. A row that only said "50 affected"
would make correlation unfalsifiable — an operator who suspected the grouping
was too broad would have nothing to check it against.

**Closing needs a reason and the flag says so.** ``--reason`` is required by the
command rather than prompted for, so a script closing an incident has to supply
one too. "Closed by Ada" does not say whether it was fixed or dismissed, and a
deployment that recorded both the same way could not find the dismissals again.
"""

from __future__ import annotations

import typer

from surfaces.cli.client import IncidentFilter
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import IncidentRecord, records_of
from surfaces.cli.output.tables import Column, Detail, table_of

app = typer.Typer(
    help="Incidents: what is wrong, and what has been done about it.",
    no_args_is_help=True,
)

detectors_app = typer.Typer(
    help="Detectors: what is being watched for, and what each one concludes.",
    no_args_is_help=True,
)

#: How many subjects a table row names before it counts the rest. Enough to
#: recognise the shape of the problem, few enough that fifty of them do not
#: push every other column off the screen.
NAMED_SUBJECTS = 3

_INCIDENT_COLUMNS = (
    Column("Incident id", weight=3),
    Column("Severity", weight=1),
    Column("State", weight=1),
    Column("Title", weight=3),
    Column("Subjects", weight=3),
    Column("Opened at", weight=2),
)

_DETECTOR_COLUMNS = (
    Column("Detector id", weight=2),
    Column("Severity", weight=1),
    Column("Signal", weight=2),
    Column("Coverage", weight=1),
    Column("Verdict", weight=1),
    Column("Enabled", weight=1),
)

_OBSERVATION_COLUMNS = (
    Column("Detector", weight=2),
    Column("Subject", weight=2),
    Column("Verdict", weight=1),
    Column("Detail", weight=4),
)

_TIMELINE_COLUMNS = (
    Column("At", weight=2),
    Column("What", weight=1),
    Column("Who", weight=2),
    Column("Why", weight=4),
)


def _subjects(record: IncidentRecord) -> str:
    """Return the subjects a table row shows, with the rest counted."""
    named = ", ".join(record.subjects[:NAMED_SUBJECTS])
    remaining = len(record.subjects) - min(len(record.subjects), NAMED_SUBJECTS)
    if remaining > 0:
        return f"{named} +{remaining}"
    return named or "—"


def _incident_rows(incidents: tuple[IncidentRecord, ...]) -> list[dict[str, object]]:
    """Return the records a table renders, in the column order above."""
    return [
        {
            "incident_id": record.incident_id,
            "severity": record.severity,
            "state": record.state,
            "title": record.title,
            "subjects": _subjects(record),
            "opened_at": record.opened_at,
        }
        for record in incidents
    ]


@app.command("list")
def list_incidents(
    ctx: typer.Context,
    state: list[str] = typer.Option([], "--state", help="Only incidents in this state."),
    severity: list[str] = typer.Option([], "--severity", help="Only incidents at this level."),
    detector: list[str] = typer.Option([], "--detector", help="Only this detector's incidents."),
    subject: str = typer.Option("", "--subject", help="Only incidents naming this resource."),
    live: bool = typer.Option(False, "--live", help="Only incidents that are still open."),
    limit: int = typer.Option(50, "--limit", help="How many to return."),
) -> None:
    """List what is wrong, most recently opened first."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_incidents(
            IncidentFilter(
                states=tuple(state),
                severities=tuple(severity),
                detectors=tuple(detector),
                subject=subject,
                live_only=live,
                limit=limit,
            )
        )
        return Output(
            command="incidents.list",
            data={"incidents": records_of(found)},
            text=table_of(
                _incident_rows(found),
                _INCIDENT_COLUMNS,
                terminal=invocation.terminal,
                empty="nothing is wrong, as far as anything has noticed",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "incidents.list", body))


@app.command("show")
def show_incident(
    ctx: typer.Context,
    incident_id: str = typer.Argument(..., help="Which incident."),
) -> None:
    """Show one incident: what it is about, and how it got where it is."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        detail = await invocation.client().show_incident(incident_id)
        incident = detail.incident
        header = Detail(
            title=f"{incident.incident_id}: {incident.title}",
            pairs=(
                ("Severity", incident.severity),
                ("State", incident.state),
                ("Raised by", f"{incident.origin} {incident.detector}".strip()),
                ("Subjects", ", ".join(incident.subjects) or "none"),
                ("Summary", incident.summary),
                ("Investigation", incident.run_id or "none started"),
                ("Closed because", incident.close_reason or "still open"),
            ),
        ).render(invocation.terminal)
        history = table_of(
            [
                {
                    "at": entry.at,
                    "kind": entry.kind,
                    "actor": entry.actor,
                    "cause": entry.cause,
                }
                for entry in detail.timeline
            ],
            _TIMELINE_COLUMNS,
            terminal=invocation.terminal,
            empty="nothing has happened to it yet",
        ).render(invocation.terminal)
        return Output(
            command="incidents.show",
            data=detail.to_record(),
            text=f"{header}\n\n{history}",
        )

    raise typer.Exit(run_command(invocation, "incidents.show", body))


@app.command("close")
def close_incident(
    ctx: typer.Context,
    incident_id: str = typer.Argument(..., help="Which incident."),
    reason: str = typer.Option(..., "--reason", help="Why it is being closed. Required."),
    resolved: bool = typer.Option(False, "--resolved", help="It was fixed, rather than dismissed."),
) -> None:
    """Close an incident, with a reason."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        closed = await invocation.client().close_incident(
            incident_id, reason=reason, resolved=resolved
        )
        return Output(
            command="incidents.close",
            data=closed.to_record(),
            text=f"{closed.incident_id} is {closed.state}: {closed.close_reason}",
        )

    raise typer.Exit(run_command(invocation, "incidents.close", body))


@app.command("suppress")
def suppress_incident(
    ctx: typer.Context,
    incident_id: str = typer.Argument(..., help="Which incident."),
    rule: str = typer.Option(..., "--rule", help="What covered it."),
    reason: str = typer.Option(..., "--reason", help="Why it is covered."),
) -> None:
    """Close an incident as suppressed, naming what covered it."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        suppressed = await invocation.client().suppress_incident(
            incident_id, rule=rule, reason=reason
        )
        return Output(
            command="incidents.suppress",
            data=suppressed.to_record(),
            text=(
                f"{suppressed.incident_id} is suppressed by "
                f"{suppressed.suppressed_by}: {suppressed.close_reason}"
            ),
        )

    raise typer.Exit(run_command(invocation, "incidents.suppress", body))


@detectors_app.command("list")
def list_detectors(ctx: typer.Context) -> None:
    """List what is being watched for, and what each detector concludes now."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_detectors()
        return Output(
            command="detectors.list",
            data={"detectors": records_of(found)},
            text=table_of(
                [
                    {
                        "detector_id": record.detector_id,
                        "severity": record.severity,
                        "signal": record.signal,
                        "coverage": f"{record.subjects_covered}/{record.subjects_total}",
                        "verdict": record.last_verdict,
                        "enabled": "yes" if record.enabled else "no",
                    }
                    for record in found
                ],
                _DETECTOR_COLUMNS,
                terminal=invocation.terminal,
                empty="nothing is being watched for; declare a detector in configuration",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "detectors.list", body))


@detectors_app.command("observations")
def list_observations(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", help="How many to return."),
) -> None:
    """Show what every enabled detector concludes right now."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        found = await invocation.client().list_observations(limit=limit)
        return Output(
            command="detectors.observations",
            data={"observations": records_of(found)},
            text=table_of(
                [
                    {
                        "detector": record.detector,
                        "subject": record.subject,
                        "verdict": record.verdict,
                        "detail": record.detail,
                    }
                    for record in found
                ],
                _OBSERVATION_COLUMNS,
                terminal=invocation.terminal,
                empty="the detectors have nothing to report",
            ).render(invocation.terminal),
        )

    raise typer.Exit(run_command(invocation, "detectors.observations", body))


@detectors_app.command("enable")
def enable_detector(
    ctx: typer.Context,
    detector_id: str = typer.Argument(..., help="Which detector."),
) -> None:
    """Turn a detector on."""
    raise typer.Exit(_toggle(ctx, detector_id, enabled=True))


@detectors_app.command("disable")
def disable_detector(
    ctx: typer.Context,
    detector_id: str = typer.Argument(..., help="Which detector."),
) -> None:
    """Turn a detector off, without unconfiguring it."""
    raise typer.Exit(_toggle(ctx, detector_id, enabled=False))


@detectors_app.command("dry-run")
def dry_run_detector(
    ctx: typer.Context,
    detector_id: str = typer.Argument(..., help="Which detector."),
) -> None:
    """Show what a detector would conclude against stored signals, firing nothing."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        run = await invocation.client().dry_run_detector(detector_id)
        table = table_of(
            [
                {
                    "detector": entry.detector,
                    "subject": entry.subject,
                    "verdict": entry.verdict,
                    "detail": entry.detail,
                }
                for entry in run.observations
            ],
            _OBSERVATION_COLUMNS,
            terminal=invocation.terminal,
            empty="this detector has nothing to read",
        ).render(invocation.terminal)
        headline = (
            f"{detector_id} would raise" if run.would_fire else f"{detector_id} would not raise"
        )
        return Output(
            command="detectors.dry-run",
            data=run.to_record(),
            text=f"{headline}. Nothing was fired.\n\n{table}",
        )

    raise typer.Exit(run_command(invocation, "detectors.dry-run", body))


def _toggle(ctx: typer.Context, detector_id: str, *, enabled: bool) -> int:
    """Turn a detector on or off and report what it now reads as."""
    invocation: Invocation = ctx.obj
    command = "detectors.enable" if enabled else "detectors.disable"

    async def body() -> Output:
        detector = await invocation.client().set_detector_enabled(detector_id, enabled=enabled)
        state = "enabled" if detector.enabled else "disabled"
        return Output(
            command=command,
            data=detector.to_record(),
            text=f"{detector.detector_id} is {state}",
        )

    return run_command(invocation, command, body)


__all__ = ["app", "detectors_app"]

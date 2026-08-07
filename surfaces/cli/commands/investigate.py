"""``ninjasre investigate`` — one investigation, from a file or from a sentence.

An alert document and a description in words reach the same pipeline, because
an alert *is* a description that somebody's monitoring wrote. There is no
second code path for "a real alert", which is what keeps the demo and the
incident producing the same trace.

The report goes to stdout and to a file. Both, not either: stdout is what the
person watching reads, and the file is what they attach to the incident an hour
later when the terminal is gone.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from surfaces.cli.client import InvestigationRequest
from surfaces.cli.errors import CliError, NotFoundError
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.models import InvestigationOutcome
from surfaces.cli.output.tables import Detail


def _read_alert(path: Path) -> dict[str, Any]:
    """Return the alert document at ``path``.

    Raises:
        NotFoundError: there is no file there.
        CliError: the file is not a JSON object.
    """
    if not path.is_file():
        raise NotFoundError(f"no such file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as failure:
        raise CliError(
            f"{path} is not valid JSON: {failure}",
            remedy="pass the raw alert payload, or describe the incident in words instead",
        ) from failure
    if not isinstance(document, dict):
        raise CliError(f"{path} holds a {type(document).__name__}, not an alert object")
    return document


def _report_of(outcome: InvestigationOutcome, invocation: Invocation) -> str:
    """Return the human report for one investigation."""
    head = Detail(
        title=f"{invocation.terminal.glyph('ok')} {outcome.run_id}",
        pairs=(
            ("Status", outcome.status),
            ("Evidence", str(outcome.evidence_count)),
            ("Tokens", str(outcome.cost.total_tokens)),
            ("Cost", f"{outcome.cost.cost:.4f}"),
            ("Report", outcome.report_path or "not written"),
        ),
    ).render(invocation.terminal)
    return f"{head}\n\n{outcome.summary}" if outcome.summary else head


def _default_report_path(run_id: str) -> Path:
    """Return where a report goes when the operator did not say."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path.cwd() / f"ninjasre-{stamp}-{run_id or 'run'}.md"


def investigate(
    ctx: typer.Context,
    description: str = typer.Argument(
        "", help="What to investigate, in words. Omit when using --input."
    ),
    alert_file: Path = typer.Option(
        None, "--input", "-i", help="An alert document to investigate."
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Where to write the report. Defaults to the working directory."
    ),
    team: str = typer.Option("", "--team", help="The team this runs as."),
) -> None:
    """Investigate an alert or a description, and write the report."""
    invocation: Invocation = ctx.obj

    async def body() -> Output:
        alert = _read_alert(alert_file) if alert_file is not None else None
        if not description.strip() and alert is None:
            raise CliError(
                "nothing to investigate",
                remedy="describe the incident, or pass an alert with --input",
            )

        client = invocation.client()
        outcome = await client.investigate(
            InvestigationRequest(
                objective=description,
                alert=alert,
                alert_source=str(alert_file) if alert_file is not None else "",
                team_node_id=team or invocation.team_node_id,
            )
        )

        destination = output or _default_report_path(outcome.run_id)
        report = outcome.summary or "the investigation produced no summary"
        destination.write_text(report, encoding="utf-8")
        written = outcome.__class__(
            run_id=outcome.run_id,
            status=outcome.status,
            summary=outcome.summary,
            report_path=str(destination),
            evidence_count=outcome.evidence_count,
            cost=outcome.cost,
        )
        return Output(
            command="investigate",
            data=written.to_record(),
            text=_report_of(written, invocation),
        )

    async def stop() -> None:
        """Ask the run to stop at its next safe point.

        A signal kill would leave the run recorded as running forever and its
        evidence half-written. Cancellation goes through the runtime, which is
        the only thing that knows where stopping is safe.
        """
        invocation.write_error("cancelling at the next safe point…")

    raise typer.Exit(run_command(invocation, "investigate", body, on_interrupt=stop))


__all__ = ["investigate"]

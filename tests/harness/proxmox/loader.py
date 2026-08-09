"""Turning a directory into a scenario, and refusing the ones that are not.

Discovery walks. There is no index, for the same reason the general corpus has
none: a list is a merge conflict on every contribution and a line somebody
eventually forgets, and a scenario that exists but was never listed fails in the
most expensive way available — by being quietly absent from the number.

Two decisions about the document itself.

**Recorded runs may say ``like``.** A scenario has four cells to fill — two model
profiles under two ablation arms — and on most of them the frontier model behaves
the same with memory and without. Writing that transcript twice is two chances
for them to drift apart in a way nobody meant, and a reader comparing the arms
would have to diff prose to find out they were identical. ``like`` names the cell
to copy and states only what differs.

**The recorded responses may live in their own file.** ``readings.json`` is what
the capture writes when a scenario's fixtures are regenerated from the
laboratory, so regeneration overwrites one machine-written document rather than
editing a hand-written one around it. Anything the declaration states inline is
layered on top, which is how a scenario keeps the one reading it is *about*
legible next to its prose.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from config.constants.hypervisor_scenarios import (
    HYPERVISOR_READINGS_FILENAME,
    HYPERVISOR_SCENARIO_FILENAME,
    HYPERVISOR_SCENARIO_SCHEMA_VERSION,
    SCENARIO_MODE_FIXTURE,
)
from tests.harness.proxmox.declaration import (
    CorrectResponse,
    Fixtures,
    LaboratorySetup,
    ReadingsPlan,
    RedHerring,
    Scenario,
    ScenarioError,
    ToolCall,
)
from tests.harness.proxmox.transcripts import ProposedAction, RecordedRun
from tests.harness.proxmox.verdicts import ResponseKind


def _read_yaml(path: Path) -> Mapping[str, Any]:
    """Return the mapping at ``path``, or raise naming the file.

    Raises:
        ScenarioError: the file is missing, unreadable, or is not a mapping.
    """
    import yaml

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ScenarioError(path.parent.name, f"{path} could not be read: {error}") from error
    except yaml.YAMLError as error:
        raise ScenarioError(path.parent.name, f"{path} is not valid YAML: {error}") from error
    if not isinstance(document, Mapping):
        raise ScenarioError(path.parent.name, f"{path} must be a mapping of fields")
    return document


def _responses(directory: Path, declared: Mapping[str, Any]) -> dict[str, Any]:
    """Return the recorded overlay: the captured file, then whatever is inline."""
    captured: dict[str, Any] = {}
    recorded = directory / HYPERVISOR_READINGS_FILENAME
    if recorded.exists():
        try:
            loaded = json.loads(recorded.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ScenarioError(directory.name, f"{recorded} is not valid JSON: {error}") from error
        if not isinstance(loaded, Mapping):
            raise ScenarioError(directory.name, f"{recorded} must map an API path to its response")
        captured.update(loaded)
    captured.update(declared)
    return captured


def _fixtures(directory: Path, document: Mapping[str, Any]) -> Fixtures:
    """Return where this scenario's readings come from."""
    declared = document.get("fixtures") or {}
    if not isinstance(declared, Mapping):
        raise ScenarioError(directory.name, "'fixtures' must be a mapping")
    inline = declared.get("responses") or {}
    if not isinstance(inline, Mapping):
        raise ScenarioError(directory.name, "'fixtures.responses' must map an API path to a body")
    return Fixtures(
        cluster_state=str(declared.get("cluster_state", "healthy")),
        responses=_responses(directory, inline),
        unreachable=bool(declared.get("unreachable", False)),
    )


def _plan(directory: Path, document: Mapping[str, Any]) -> ReadingsPlan:
    """Return the tools this scenario runs and what they have to report."""
    declared = document.get("readings") or {}
    if not isinstance(declared, Mapping):
        raise ScenarioError(directory.name, "'readings' must be a mapping")
    calls: list[ToolCall] = []
    for entry in declared.get("tools") or ():
        if isinstance(entry, str):
            calls.append(ToolCall(name=entry))
            continue
        if not isinstance(entry, Mapping) or "name" not in entry:
            raise ScenarioError(directory.name, "each entry of 'readings.tools' needs a name")
        calls.append(
            ToolCall(name=str(entry["name"]), arguments=dict(entry.get("arguments") or {}))
        )
    return ReadingsPlan(
        tools=tuple(calls),
        must_report=tuple(str(found) for found in declared.get("must_report") or ()),
    )


def _response(directory: Path, document: Mapping[str, Any]) -> CorrectResponse:
    """Return what the scenario says the correct response was."""
    declared = document.get("response")
    if not isinstance(declared, Mapping):
        raise ScenarioError(
            directory.name,
            "a scenario has to declare the correct response; a scenario that scores an action "
            "without saying what the right one was is scoring an opinion",
        )
    try:
        return CorrectResponse(
            kind=ResponseKind(str(declared.get("kind", ""))),
            why=str(declared.get("why", "")),
            capability=str(declared.get("capability", "")),
        )
    except ValueError as error:
        raise ScenarioError(directory.name, f"'response' is not usable: {error}") from error


def _truth(directory: Path, document: Mapping[str, Any]):  # noqa: ANN202 - returns Truth
    """Return the cause and the evidence a correct diagnosis rests on."""
    from tests.harness.proxmox.declaration import Truth

    declared = document.get("truth")
    if not isinstance(declared, Mapping):
        raise ScenarioError(directory.name, "a scenario has to declare the true root cause")
    try:
        return Truth(
            root_cause=str(declared.get("root_cause", "")),
            evidence=tuple(str(found) for found in declared.get("evidence") or ()),
            insufficient=bool(declared.get("insufficient", False)),
            summary=str(declared.get("summary", "")),
        )
    except ValueError as error:
        raise ScenarioError(directory.name, f"'truth' is not usable: {error}") from error


def _laboratory(directory: Path, document: Mapping[str, Any]) -> LaboratorySetup | None:
    """Return how a destructive scenario is produced and undone, when it is one."""
    declared = document.get("laboratory")
    if declared is None:
        return None
    if not isinstance(declared, Mapping):
        raise ScenarioError(directory.name, "'laboratory' must be a mapping")
    try:
        return LaboratorySetup(
            fault=str(declared.get("fault", "")),
            restore=str(declared.get("restore", "")),
            disables=tuple(str(found) for found in declared.get("disables") or ()),
        )
    except ValueError as error:
        raise ScenarioError(directory.name, f"'laboratory' is not usable: {error}") from error


def _action(declared: Any) -> ProposedAction:
    """Return the action one recorded run proposed."""
    if declared is None:
        return ProposedAction(kind=ResponseKind.NONE)
    if isinstance(declared, str):
        return ProposedAction(kind=ResponseKind(declared))
    if not isinstance(declared, Mapping):
        raise ValueError("a run's 'action' must be a kind or a mapping of kind and capability")
    return ProposedAction(
        kind=ResponseKind(str(declared.get("kind", "none"))),
        capability=str(declared.get("capability", "")),
    )


def _run(
    directory: Path, declared: Mapping[str, Any], known: Mapping[str, RecordedRun]
) -> RecordedRun:
    """Return one recorded run, resolving ``like`` against the cells already read."""
    fields: dict[str, Any] = {}
    named = declared.get("like")
    if named is not None:
        parent = known.get(str(named))
        if parent is None:
            raise ScenarioError(
                directory.name,
                f"a run says it is like {named!r}, and no cell of that name is declared above it; "
                f"declared so far: {', '.join(known) or 'none'}",
            )
        fields = {
            "completed": parent.completed,
            "diagnosis": parent.diagnosis,
            "cited": parent.cited,
            "said_insufficient": parent.said_insufficient,
            "action": parent.action,
            "took": parent.took,
            "transcript": parent.transcript,
            "incomplete_reason": parent.incomplete_reason,
        }

    if "completed" in declared:
        fields["completed"] = bool(declared["completed"])
    if "diagnosis" in declared:
        fields["diagnosis"] = str(declared["diagnosis"])
    if "cited" in declared:
        fields["cited"] = tuple(str(found) for found in declared["cited"] or ())
    if "said_insufficient" in declared:
        fields["said_insufficient"] = bool(declared["said_insufficient"])
    if "action" in declared:
        fields["action"] = _action(declared["action"])
    if "took" in declared:
        fields["took"] = tuple(str(found) for found in declared["took"] or ())
    if "transcript" in declared:
        fields["transcript"] = str(declared["transcript"])
    if "incomplete_reason" in declared:
        fields["incomplete_reason"] = str(declared["incomplete_reason"])

    try:
        return RecordedRun(model=str(declared["model"]), arm=str(declared["arm"]), **fields)
    except (KeyError, ValueError) as error:
        raise ScenarioError(directory.name, f"a recorded run is not usable: {error}") from error


def _runs(directory: Path, document: Mapping[str, Any]) -> tuple[RecordedRun, ...]:
    """Return every recorded run this scenario ships, in declared order."""
    declared = document.get("runs") or ()
    if not isinstance(declared, Sequence) or isinstance(declared, str):
        raise ScenarioError(directory.name, "'runs' must be a list of recorded runs")
    known: dict[str, RecordedRun] = {}
    for entry in declared:
        if not isinstance(entry, Mapping):
            raise ScenarioError(directory.name, "each entry of 'runs' must be a mapping")
        run = _run(directory, entry, known)
        if run.cell in known:
            raise ScenarioError(directory.name, f"declares the cell {run.cell} twice")
        known[run.cell] = run
    if not known:
        raise ScenarioError(
            directory.name,
            "ships no recorded run, so there is nothing to score; a scenario with no transcript "
            "is a description rather than a measurement",
        )
    return tuple(known.values())


def load_scenario(directory: Path) -> tuple[Scenario, tuple[RecordedRun, ...]]:
    """Return the scenario in ``directory`` and every run recorded against it.

    Raises:
        ScenarioError: the declaration is missing, malformed, or incomplete.
    """
    directory = Path(directory)
    document = _read_yaml(directory / HYPERVISOR_SCENARIO_FILENAME)

    version = str(document.get("schema_version", ""))
    if version != HYPERVISOR_SCENARIO_SCHEMA_VERSION:
        raise ScenarioError(
            directory.name,
            f"declares schema version {version!r}; this loader reads "
            f"{HYPERVISOR_SCENARIO_SCHEMA_VERSION!r} and will not guess at another",
        )

    modes = tuple(str(found) for found in document.get("modes") or (SCENARIO_MODE_FIXTURE,))
    scenario = Scenario(
        scenario_id=str(document.get("scenario_id", "")),
        domain=str(document.get("domain", "")),
        title=str(document.get("title", "")),
        situation=str(document.get("situation", "")),
        truth=_truth(directory, document),
        response=_response(directory, document),
        difficulty=int(document.get("difficulty", 2)),
        modes=modes,
        fixtures=_fixtures(directory, document),
        readings=_plan(directory, document),
        laboratory=_laboratory(directory, document),
        red_herrings=tuple(
            RedHerring(
                name=str(found.get("name", "")),
                why=str(found.get("why", "")),
                tempting=str(found.get("tempting", "")),
            )
            for found in document.get("red_herrings") or ()
        ),
        exercises=tuple(str(found) for found in document.get("exercises") or ()),
        postmortem=str(document.get("postmortem", "")),
        directory=directory,
    )
    return scenario, _runs(directory, document)


def discover(root: Path) -> tuple[tuple[Scenario, tuple[RecordedRun, ...]], ...]:
    """Return every scenario under ``root``, ordered by domain then identifier.

    A directory holding no declaration is not a scenario and is passed over in
    silence — notes, captures and ``__pycache__`` all live perfectly well beside
    a corpus.
    """
    root = Path(root)
    if not root.exists():
        return ()
    found = [
        load_scenario(path.parent) for path in sorted(root.rglob(HYPERVISOR_SCENARIO_FILENAME))
    ]
    return tuple(sorted(found, key=lambda pair: (pair[0].domain, pair[0].scenario_id)))


__all__ = ["discover", "load_scenario"]

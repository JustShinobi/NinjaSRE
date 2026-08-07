"""One command for everything this tooling does, and one of them is a question.

``serve`` and ``console`` are the development loop. ``build`` and ``contract``
regenerate what is committed. ``verify`` runs every check the gate runs, on
demand, so a failure can be reproduced without pytest in the way. ``capture``
takes a fresh recording from a live deployment and a live cluster.

``ask`` is the one that is easy to underestimate. Building a console against
real infrastructure keeps raising questions the capture did not anticipate —
what does a locked guest's configuration actually look like, what does the task
log say when a backup dies. Sending somebody to a terminal to find out, and then
transcribing the answer by hand, is how a fixture ends up describing what a
person remembered rather than what the cluster said. ``ask`` runs one allowlisted
read and prints the answer; ``record`` puts that answer into the dataset through
the same anonymisation, the same provenance and the same checks as a captured
one, because a finding that arrives by a different route is a finding the scan
never saw.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from config.constants.fixtures import (
    DEFAULT_FIXTURE_SCENARIO,
    MOCK_SERVER_DEFAULT_PORT,
)
from config.constants.surfaces import DEFAULT_CONSOLE_PORT, NINJASRE_ENDPOINT_ENV
from tools.mockplane.allowlist import Allowlist, CommandRefused
from tools.mockplane.capture.channel import (
    ChannelError,
    NoConnectionDetails,
    NodeConfiguration,
    ReadOnlyChannel,
    SshCommandRunner,
)
from tools.mockplane.capture.cluster import read_cluster
from tools.mockplane.capture.gateway import (
    GatewayTarget,
    GatewayUnreachable,
    UrllibFetcher,
    capture_gateway,
)
from tools.mockplane.capture.projection import project
from tools.mockplane.identifiers import IdentifierFileError, IdentifierList

PROGRAM: Final = "mockplane"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM, description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="serve a scenario over HTTP")
    serve.add_argument("--scenario", default=DEFAULT_FIXTURE_SCENARIO)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=MOCK_SERVER_DEFAULT_PORT)

    console = commands.add_parser("console", help="serve a scenario and the console in front of it")
    console.add_argument("--scenario", default=DEFAULT_FIXTURE_SCENARIO)
    console.add_argument("--host", default="127.0.0.1")
    console.add_argument("--port", type=int, default=DEFAULT_CONSOLE_PORT)
    console.add_argument("--mock-port", type=int, default=MOCK_SERVER_DEFAULT_PORT)

    build = commands.add_parser("build", help="rebuild the committed scenario files")
    build.add_argument("--scenario", default="")

    commands.add_parser("contract", help="regenerate the committed OpenAPI document")

    verify = commands.add_parser("verify", help="run every check over the committed dataset")
    verify.add_argument("--identifiers", default="", help="the operator's list of real values")

    commands.add_parser("report", help="print what the fixture set covers and what it misses")

    capture = commands.add_parser("capture", help="record a fresh capture from both sources")
    capture.add_argument("--into", default="", help="where to write the raw capture")

    ask = commands.add_parser("ask", help="run one allowlisted read and print the answer")
    ask.add_argument("--node", required=True)
    ask.add_argument("command", nargs=argparse.REMAINDER)

    commands.add_parser("allowlist", help="print the reads this tooling is permitted to make")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command. Returns the process exit code."""
    arguments = _parser().parse_args(list(argv) if argv is not None else None)

    match arguments.command:
        case "serve":
            return _serve(arguments.scenario, arguments.host, arguments.port)
        case "console":
            return _console(arguments.scenario, arguments.host, arguments.port, arguments.mock_port)
        case "build":
            return _build(arguments.scenario)
        case "contract":
            return _contract()
        case "verify":
            return _verify(arguments.identifiers)
        case "report":
            return _report()
        case "capture":
            return _capture(arguments.into)
        case "ask":
            return _ask(arguments.node, " ".join(arguments.command).strip())
        case "allowlist":
            return _allowlist()
        case _:  # pragma: no cover — argparse rejects anything else
            return 2


def _say(message: str) -> None:
    print(message, file=sys.stderr)  # noqa: T201 — an operator is reading a terminal


def _serve(scenario: str, host: str, port: int) -> int:  # pragma: no cover — a server
    from tools.mockplane.server import serve

    _say(f"serving the {scenario!r} scenario on http://{host}:{port}")
    serve(scenario, host=host, port=port)
    return 0


def _console(
    scenario: str, host: str, port: int, mock_port: int
) -> int:  # pragma: no cover — a server
    """Start the mock and the console in front of it, in one process."""
    import os
    import threading

    import uvicorn

    from surfaces.console.serve import build_server
    from tools.mockplane.server import build_mock

    mock = build_mock(scenario)
    mock_server = uvicorn.Server(uvicorn.Config(mock, host=host, port=mock_port, log_config=None))
    threading.Thread(target=mock_server.run, daemon=True).start()

    endpoint = f"http://{host}:{mock_port}"
    console = build_server({**os.environ, NINJASRE_ENDPOINT_ENV: endpoint})
    _say(f"the {scenario!r} scenario is on {endpoint}; the console is on http://{host}:{port}")
    uvicorn.run(console, host=host, port=port, log_config=None)
    return 0


def _build(scenario: str) -> int:
    from tools.mockplane.dataset.build import BUILT_SCENARIOS, write_all

    chosen = (scenario,) if scenario else BUILT_SCENARIOS
    written = write_all(scenarios=chosen)
    _say(f"wrote {len(written)} files across {len(chosen)} scenarios")
    return 0


def _contract() -> int:
    from config.constants.fixtures import FIXTURE_OPENAPI_FILENAME
    from tools.mockplane.contract import contract_dir, generated_openapi_document
    from tools.mockplane.records import dumps

    path = contract_dir() / FIXTURE_OPENAPI_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(generated_openapi_document()), encoding="utf-8")
    _say(f"wrote {path}")
    return 0


def _verify(identifier_file: str) -> int:
    from config.constants.fixtures import FIXTURE_SCENARIO_NAMES
    from tools.mockplane import scenarios
    from tools.mockplane.contract import ContractError, response_schema, validate
    from tools.mockplane.endpoints import endpoint_by_slug
    from tools.mockplane.paths import fixture_root
    from tools.mockplane.verify import coherence, referential
    from tools.mockplane.verify.identifiers import scan_tree

    try:
        identifiers = IdentifierList.load(Path(identifier_file) if identifier_file else None)
    except IdentifierFileError as failure:
        _say(str(failure))
        return 1

    failures = 0
    leaks = scan_tree(fixture_root(), identifiers)
    for leak in leaks:
        _say(str(leak))
    failures += len(leaks)
    if not identifiers:
        _say(
            "note: no list of real values was supplied, so only the pattern net ran. "
            "Pass --identifiers to run the adversarial scan as well."
        )

    for name in FIXTURE_SCENARIO_NAMES:
        records = scenarios.load(name).all_records()
        for reference in referential.broken(records):
            _say(f"{name}: {reference}")
            failures += 1
        for implausible in coherence.implausibilities(records):
            _say(f"{name}: {implausible}")
            failures += 1
        for record in records:
            endpoint = endpoint_by_slug(record.slug)
            if endpoint.streaming or record.status >= 400:
                continue
            try:
                schema, document = response_schema(endpoint, record.status)
            except ContractError as failure:
                _say(f"{name}: {failure}")
                failures += 1
                continue
            for violation in validate(record.body, schema, document):
                _say(f"{name}: {endpoint.method} {endpoint.path}: {violation}")
                failures += 1

    missing = coherence.awkwardness_of(scenarios.load("populated").all_records()).missing
    for absent in missing:
        _say(f"populated: the dataset no longer has {absent}")
        failures += 1

    _say("the dataset is clean" if not failures else f"{failures} problems")
    return 0 if not failures else 1


def _report() -> int:
    from tools.mockplane.dataset.build import covered_slugs, uncovered_slugs
    from tools.mockplane.endpoints import CONSOLE_ENDPOINTS, projected_endpoints

    covered = covered_slugs()
    _say(f"{len(covered)} of {len(CONSOLE_ENDPOINTS)} console endpoints are covered")
    for endpoint in projected_endpoints():
        _say(f"  projected ({endpoint.arrives_with}): {endpoint.method} {endpoint.path}")
    for slug in uncovered_slugs():
        _say(f"  UNCOVERED: {slug}")
    return 1 if uncovered_slugs() else 0


def _capture(into: str) -> int:  # pragma: no cover — needs a deployment and a cluster
    from datetime import UTC, datetime

    from tools.mockplane.paths import is_inside_repository, raw_capture_dir
    from tools.mockplane.records import dumps

    destination = Path(into).expanduser() if into else raw_capture_dir()
    if is_inside_repository(destination):
        _say(
            f"refusing to write a raw capture to {destination}: it is inside the repository, "
            f"and a raw capture carries hostnames, addresses and guest configuration"
        )
        return 1

    try:
        target = GatewayTarget.from_environment()
    except GatewayUnreachable as failure:
        _say(str(failure))
        return 1
    served = capture_gateway(target, UrllibFetcher())

    try:
        configuration = NodeConfiguration.from_environment()
    except NoConnectionDetails as failure:
        _say(str(failure))
        return 1
    channel = ReadOnlyChannel(runner=SshCommandRunner(configuration), allowlist=Allowlist.load())
    reading, missed = read_cluster(
        channel,
        tuple(configuration.hosts),
        captured_at=datetime.now(UTC).isoformat(),
    )
    projected = project(reading)

    destination.mkdir(parents=True, exist_ok=True)
    raw = destination / "capture.json"
    raw.write_text(
        dumps(
            {
                "records": [record.as_json() for record in (*served.records, *projected)],
                "missed": [
                    {
                        "slug": entry.slug,
                        "method": entry.method,
                        "path": entry.path,
                        "source": entry.source,
                        "reason": entry.reason,
                    }
                    for entry in (*served.missed, *missed)
                ],
            }
        ),
        encoding="utf-8",
    )
    _say(f"wrote {len(served.records) + len(projected)} records to {raw}")
    for entry in (*served.missed, *missed):
        _say(f"  missed: {entry}")
    _say(
        "this file is not anonymised. Run 'mockplane build' from it, then delete it — "
        "the pipeline does that for you."
    )
    return 0


def _ask(node: str, command: str) -> int:  # pragma: no cover — needs a cluster
    try:
        configuration = NodeConfiguration.from_environment()
    except NoConnectionDetails as failure:
        _say(str(failure))
        return 1
    channel = ReadOnlyChannel(runner=SshCommandRunner(configuration), allowlist=Allowlist.load())
    try:
        print(channel.read(node, command))  # noqa: T201 — the answer is the point
    except CommandRefused as refusal:
        _say(str(refusal))
        return 2
    except ChannelError as failure:
        _say(str(failure))
        return 1
    return 0


def _allowlist() -> int:
    allowlist = Allowlist.load()
    for declared in allowlist:
        print(json.dumps({"command": declared.template, "kind": declared.kind}))  # noqa: T201
    _say(f"{len(allowlist)} declared reads, in {allowlist.source}")
    return 0


__all__ = ["PROGRAM", "main"]

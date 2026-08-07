"""``python -m tests.e2e`` — the demo suite, the cloud suite, and the reaper.

``reap`` is the one worth reading about. It is the only verb here that is meant
to be run on a schedule by something nobody is watching, so it defaults to
reporting rather than destroying: the first time anybody points this at an
account, what they want is a list. ``--destroy`` is the second run.

``demo`` and ``cloud`` take an investigator for the same reason the chaos suite
does — composing one needs a provider and the operator's own credential proxy,
which is a deployment question rather than a suite one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from config.constants.chaos import (
    NINJASRE_CHAOS_CONTEXT_ENV,
    NINJASRE_CHAOS_KUBECONFIG_ENV,
    OTEL_DEMO_NAMESPACE,
)
from tests.chaos.__main__ import SKIPPED, _investigator
from tests.chaos.framework.cluster import cluster_availability, skip_reason
from tests.chaos.framework.kubectl import KubectlCluster
from tests.e2e.cloud.provisioning import DeclarativeProvisioner, ProvisioningError
from tests.e2e.cloud.reaper import reap
from tests.e2e.cloud.runner import run_scenarios
from tests.e2e.cloud.scenarios import discover_scenarios
from tests.e2e.cloud.signals import CloudSignals
from tests.e2e.otel_demo.faults import discover_faults
from tests.e2e.otel_demo.injection import FlagdFaults
from tests.e2e.otel_demo.install import DemoInstallation, install, uninstall
from tests.e2e.otel_demo.runner import run_faults
from tests.support.commands import CommandFailed, SubprocessRunner


def _cluster(arguments: argparse.Namespace) -> KubectlCluster:
    return KubectlCluster(
        runner=SubprocessRunner(), context=arguments.context, kubeconfig=arguments.kubeconfig
    )


def _demo_install(arguments: argparse.Namespace) -> int:
    """Install the demo application and its observability stack."""
    try:
        report = install(SubprocessRunner(), DemoInstallation(namespace=arguments.namespace))
    except CommandFailed as failure:
        print(str(failure), file=sys.stderr)
        return 1
    if report.missing:
        print(f"installed, but not ready: {', '.join(report.missing)}", file=sys.stderr)
        return 1
    print("the demo application and its observability stack are ready")
    return 0


def _demo_uninstall(arguments: argparse.Namespace) -> int:
    """Remove the demo application."""
    result = uninstall(SubprocessRunner(), DemoInstallation(namespace=arguments.namespace))
    print("removed" if result.ok else f"could not remove it: {result.message}")
    return 0 if result.ok else 1


def _demo_run(arguments: argparse.Namespace) -> int:
    """Enable each fault in turn, investigate it, and score the run."""
    availability = cluster_availability(kubeconfig=arguments.kubeconfig, context=arguments.context)
    if not availability.available:
        print(skip_reason(availability), file=sys.stderr)
        return SKIPPED

    faults = discover_faults()
    if arguments.fault:
        faults = tuple(found for found in faults if arguments.fault in found.fault_id)
    if not faults:
        print(f"no fault matches {arguments.fault!r}", file=sys.stderr)
        return 1

    report, outcomes = asyncio.run(
        run_faults(
            faults,
            cluster=_cluster(arguments),
            faults=FlagdFaults(runner=SubprocessRunner(), namespace=arguments.namespace),
            investigator=_investigator(arguments.investigator),
            run_id=arguments.run_id or uuid.uuid4().hex[:8],
        )
    )
    print(report.render())
    _write(arguments.artifacts, report.to_record(), [found.to_record() for found in outcomes])
    return 0 if not report.agent_failures else 1


def _cloud_run(arguments: argparse.Namespace) -> int:
    """Provision each scenario, investigate it, score it, and tear it down."""
    if not os.environ.get("NINJASRE_E2E_CLOUD"):
        print(
            "the cloud suite provisions real infrastructure; set NINJASRE_E2E_CLOUD=1 to "
            "confirm you mean to spend money",
            file=sys.stderr,
        )
        return SKIPPED

    scenarios = discover_scenarios()
    if arguments.scenario:
        scenarios = tuple(found for found in scenarios if arguments.scenario in found.scenario_id)
    if not scenarios:
        print(f"no scenario matches {arguments.scenario!r}", file=sys.stderr)
        return 1

    run_id = arguments.run_id or uuid.uuid4().hex[:8]
    runner = SubprocessRunner()
    report, cost, outcomes = asyncio.run(
        run_scenarios(
            scenarios,
            provisioner=DeclarativeProvisioner(runner=runner),
            signals=CloudSignals(runner=runner, run_id=run_id),
            investigator=_investigator(arguments.investigator),
            run_id=run_id,
        )
    )
    print(report.render())
    print()
    print(cost.render())
    _write(arguments.artifacts, report.to_record(), [found.to_record() for found in outcomes])

    leaked = [found.scenario_id for found in outcomes if not found.clean]
    if leaked:
        print(f"\nleft behind by {leaked}; run 'make e2e-reap'", file=sys.stderr)
        return 2
    if not cost.within:
        print(f"\nover the declared bound: {cost.over_bound}", file=sys.stderr)
        return 2
    return 0 if not report.agent_failures else 1


def _reap(arguments: argparse.Namespace) -> int:
    """Report — or destroy — everything a killed run left in the account."""
    try:
        report = reap(
            DeclarativeProvisioner(runner=SubprocessRunner()),
            active_runs=tuple(arguments.holding),
            dry_run=not arguments.destroy,
        )
    except ProvisioningError as failure:
        print(str(failure), file=sys.stderr)
        return 1

    print(report.render())
    if not arguments.destroy and report.reaped:
        print("\nnothing was destroyed. Run again with --destroy to remove the above.")
    return 0 if report.clean else 1


def _write(path: str, report: Any, outcomes: Any) -> None:
    """Write the run record, when one was asked for."""
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"report": report, "outcomes": outcomes}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nwritten to {destination}")


def main(argv: list[str] | None = None) -> int:
    """Run the end-to-end command line and return its exit status."""
    parser = argparse.ArgumentParser(prog="python -m tests.e2e", description=__doc__)
    parser.add_argument("--kubeconfig", default=os.environ.get(NINJASRE_CHAOS_KUBECONFIG_ENV, ""))
    parser.add_argument("--context", default=os.environ.get(NINJASRE_CHAOS_CONTEXT_ENV, ""))
    parser.add_argument("--namespace", default=OTEL_DEMO_NAMESPACE)
    parser.add_argument("--artifacts", default="", help="where to write the run record")
    verbs = parser.add_subparsers(dest="verb", required=True)

    setup = verbs.add_parser("demo-setup", help="install the demo and its stack")
    setup.set_defaults(handler=_demo_install)

    teardown = verbs.add_parser("demo-teardown", help="remove the demo")
    teardown.set_defaults(handler=_demo_uninstall)

    demo = verbs.add_parser("demo", help="run every demo fault end to end")
    demo.add_argument("--investigator", required=True)
    demo.add_argument("--fault", default="")
    demo.add_argument("--run-id", default="")
    demo.set_defaults(handler=_demo_run)

    cloud = verbs.add_parser("cloud", help="provision, investigate, and destroy")
    cloud.add_argument("--investigator", required=True)
    cloud.add_argument("--scenario", default="")
    cloud.add_argument("--run-id", default="")
    cloud.set_defaults(handler=_cloud_run)

    sweep = verbs.add_parser("reap", help="find, and optionally destroy, orphaned resources")
    sweep.add_argument(
        "--destroy", action="store_true", help="actually destroy what the sweep found"
    )
    sweep.add_argument(
        "--holding",
        nargs="*",
        default=(),
        help="run identifiers that are still live and must not be reaped",
    )
    sweep.set_defaults(handler=_reap)

    arguments = parser.parse_args(argv)
    handler: Any = arguments.handler
    status: int = handler(arguments)
    return status


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())

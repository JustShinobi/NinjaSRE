"""``python -m tests.chaos`` — list, sweep, and run the chaos suite.

Three verbs, and two of them work with nothing configured at all. ``list`` reads
the catalogue, ``sweep`` removes whatever a killed run left on the cluster, and
``run`` needs the one thing this repository cannot supply for you.

**Why ``run`` takes an investigator.** An investigation needs a provider and the
operator's own credential proxy, and composing those is a deployment question
rather than a suite one — the same seam the CLI and the REST surface already sit
behind. So ``--investigator module:factory`` names a callable in the operator's
own deployment that returns something satisfying ``Investigator``, and the suite
drives it. Guessing a composition here would produce a run against whatever
ambient configuration happened to be lying around, which is the failure mode the
whole credential design exists to prevent.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from config.constants.chaos import (
    NINJASRE_CHAOS_CONTEXT_ENV,
    NINJASRE_CHAOS_KUBECONFIG_ENV,
    NINJASRE_CHAOS_LOCK_DIR_ENV,
)
from tests.chaos.framework.catalogue import (
    EXPERIMENTS_ROOT,
    ExperimentFilter,
    discover_experiments,
)
from tests.chaos.framework.cleanup import sweep_orphans
from tests.chaos.framework.cluster import cluster_availability, skip_reason
from tests.chaos.framework.kubectl import KubectlCluster
from tests.chaos.runner import run_suite
from tests.support.commands import SubprocessRunner

#: What a clean skip exits with. Zero, deliberately: a suite that cannot run for
#: want of infrastructure has not failed, and a non-zero exit would make every
#: scheduled job on a machine without a cluster look like a regression.
SKIPPED = 0


def _cluster(arguments: argparse.Namespace) -> KubectlCluster:
    """Return the cluster this invocation acts on."""
    return KubectlCluster(
        runner=SubprocessRunner(),
        context=arguments.context,
        kubeconfig=arguments.kubeconfig,
    )


def _investigator(reference: str) -> Any:
    """Return the investigator ``module:factory`` names.

    Raises:
        SystemExit: the reference does not name a callable that can be imported.
    """
    if ":" not in reference:
        raise SystemExit(
            f"--investigator takes 'module:factory', got {reference!r}; the factory returns "
            f"whatever your deployment composes an investigation from"
        )
    module_name, _, attribute = reference.partition(":")
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute)
    except (ImportError, AttributeError) as failure:
        raise SystemExit(f"--investigator {reference!r}: {failure}") from failure
    return factory()


def _run(arguments: argparse.Namespace) -> int:
    """Run the suite and return the exit status."""
    availability = cluster_availability(kubeconfig=arguments.kubeconfig, context=arguments.context)
    if not availability.available:
        print(skip_reason(availability), file=sys.stderr)
        return SKIPPED

    experiments = ExperimentFilter(experiment_id=arguments.experiment).select(
        discover_experiments(EXPERIMENTS_ROOT)
    )
    if not experiments:
        print(f"no experiment matches {arguments.experiment!r}", file=sys.stderr)
        return 1

    report, outcomes = asyncio.run(
        run_suite(
            experiments,
            cluster=_cluster(arguments),
            investigator=_investigator(arguments.investigator),
            run_id=arguments.run_id or uuid.uuid4().hex[:8],
            lock_root=Path(arguments.lock_root),
        )
    )

    print(report.render())
    if arguments.artifacts:
        path = Path(arguments.artifacts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "report": report.to_record(),
                    "outcomes": [outcome.to_record() for outcome in outcomes],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwritten to {path}")

    dirty = [outcome for outcome in outcomes if not outcome.cleanup.clean]
    if dirty:
        print(
            "\nthe cluster is not clean; run 'make chaos-sweep' before the next run:",
            file=sys.stderr,
        )
        for outcome in dirty:
            print(f"  {outcome.experiment_id}: {outcome.cleanup.failures}", file=sys.stderr)
        return 2
    return 0 if not report.agent_failures else 1


def _sweep(arguments: argparse.Namespace) -> int:
    """Remove every fault carrying this suite's label and report what went."""
    availability = cluster_availability(kubeconfig=arguments.kubeconfig, context=arguments.context)
    if not availability.available:
        print(skip_reason(availability), file=sys.stderr)
        return SKIPPED

    swept = sweep_orphans(_cluster(arguments))
    if not swept:
        print("nothing left behind — the cluster holds no fault this suite applied")
        return 0
    print(f"removed {len(swept)} orphaned faults:")
    for identifier in swept:
        print(f"  {identifier}")
    return 0


def _list(arguments: argparse.Namespace) -> int:
    """Print the catalogue, which needs no cluster at all."""
    for experiment in discover_experiments(EXPERIMENTS_ROOT):
        declared = experiment.expectation
        print(
            f"{experiment.experiment_id:<22} {declared.expected_root_cause_category:<24} "
            f"{declared.validity_probe.check}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the chaos command line and return its exit status."""
    parser = argparse.ArgumentParser(prog="python -m tests.chaos", description=__doc__)
    parser.add_argument(
        "--kubeconfig",
        default=os.environ.get(NINJASRE_CHAOS_KUBECONFIG_ENV, ""),
        help="the kubeconfig to use (default: whatever kubectl defaults to)",
    )
    parser.add_argument(
        "--context",
        default=os.environ.get(NINJASRE_CHAOS_CONTEXT_ENV, ""),
        help="the cluster context to act on",
    )
    parser.add_argument(
        "--lock-root",
        default=os.environ.get(NINJASRE_CHAOS_LOCK_DIR_ENV, "") or ".chaos-locks",
        help="where cluster locks are held",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    run = verbs.add_parser("run", help="inject, investigate, score, and clean up")
    run.add_argument(
        "--investigator",
        required=True,
        help="module:factory returning your deployment's Investigator",
    )
    run.add_argument("--experiment", default="", help="run only experiments matching this")
    run.add_argument("--run-id", default="", help="the identifier this run is tagged with")
    run.add_argument("--artifacts", default="", help="where to write the run record")
    run.set_defaults(handler=_run)

    sweep = verbs.add_parser("sweep", help="remove faults a killed run left behind")
    sweep.set_defaults(handler=_sweep)

    listing = verbs.add_parser("list", help="print the experiment catalogue")
    listing.set_defaults(handler=_list)

    arguments = parser.parse_args(argv)
    handler: Any = arguments.handler
    status: int = handler(arguments)
    return status


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())

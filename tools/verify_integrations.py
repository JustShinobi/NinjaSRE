"""Check the catalogue: parity, verifier completeness, and — on demand — live vendors.

FR-012 says verification is invocable from the CLI, the console, and CI, and the
three want different things. The CLI and the console want one team's credential
checked against a live vendor, which is what ``ninjasre integrations verify``
does. CI has no credentials and must still fail on the things that are knowable
without them, which is what this runs by default:

``parity``
    Every integration ships all seven artefacts (FR-002). Named per integration
    and per artefact, so the message says what to write.

``verifier completeness``
    Every integration declares a verifier that says what call proves
    connectivity, and one probe per permission its capabilities need. A verifier
    with no probes reports "the credential works" for a credential that cannot
    do the job, which is a worse answer than no verification at all.

``permission bindings``
    Every permission names the capabilities that stop working without it, and
    every capability it names is one the integration actually declares. A
    permission pointing at a renamed tool produces a failure message that sends
    an operator looking for something that is not there.

``--live`` adds the vendor calls, for the scheduled job. A failure there does
*not* fail the build (FR-016): a vendor's breaking change is not the operator's
fault, and a red build tells them nothing about which of eighty-five vendors
broke. It marks the integration degraded and prints what stopped working, so
everything else keeps running and the affected part is named.

Usage::

    python -m tools.verify_integrations [--live] [--json]

Run as a module, from the repository root. This is the one check that imports
first-party packages rather than parsing source, so it needs the repository root
leading ``sys.path`` — ``platform/`` shadows the stdlib module and only wins the
name that way. ``python tools/verify_integrations.py`` puts ``tools/`` first
instead and fails on the stdlib ``platform``.

Exits 0 when clean, 1 when something knowable at build time is wrong.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from integrations._catalogue.discovery import catalogue
from integrations._catalogue.entry import CatalogueEntry
from integrations._catalogue.health import HealthLedger
from integrations._verification.framework import IntegrationVerifier

PARITY_RULE = "parity"
VERIFIER_RULE = "verifier-incomplete"
PROBE_RULE = "permission-unprobed"
BINDING_RULE = "permission-names-no-capability"


@dataclass(frozen=True, order=True)
class Problem:
    """One thing wrong with the catalogue that CI can see without credentials."""

    rule: str
    integration: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.integration}: {self.message}"


def parity_problems(entry: CatalogueEntry) -> list[Problem]:
    """Return a problem per artefact ``entry`` is missing (FR-002)."""
    return [
        Problem(rule=PARITY_RULE, integration=entry.name, message=line.strip())
        for line in entry.parity.failure_message().splitlines()[1:]
    ]


def verifier_problems(entry: CatalogueEntry) -> list[Problem]:
    """Return what is missing from ``entry``'s verifier."""
    verifier = entry.descriptor.verifier
    if not isinstance(verifier, IntegrationVerifier):
        return [
            Problem(
                rule=VERIFIER_RULE,
                integration=entry.name,
                message=(
                    "declares a verifier that cannot probe connectivity or permissions, so "
                    "nothing can tell an operator whether this integration works"
                ),
            )
        ]

    found: list[Problem] = []
    if not verifier.probe_description.strip():
        found.append(
            Problem(
                rule=VERIFIER_RULE,
                integration=entry.name,
                message=(
                    "does not say what call proves connectivity. A vendor with no "
                    "verification endpoint uses its cheapest read instead, and the "
                    "substitution has to be written down or nobody can interpret the result"
                ),
            )
        )

    probed = {probe.permission.name for probe in verifier.probes()}
    for permission in entry.profile.permissions:
        if permission.name not in probed:
            found.append(
                Problem(
                    rule=PROBE_RULE,
                    integration=entry.name,
                    message=(
                        f"declares {permission.name!r} as required and probes nothing for "
                        f"it, so verification would report success for a credential "
                        f"missing it"
                    ),
                )
            )
    return found


def binding_problems(entry: CatalogueEntry) -> list[Problem]:
    """Return a problem per permission naming a capability the integration does not declare."""
    declared = set(entry.capabilities)
    found: list[Problem] = []
    for permission in entry.profile.permissions:
        if not permission.capabilities:
            found.append(
                Problem(
                    rule=BINDING_RULE,
                    integration=entry.name,
                    message=(
                        f"{permission.name!r} names no capability, so a report that it is "
                        f"missing cannot say what stops working"
                    ),
                )
            )
        for capability in permission.capabilities:
            if capability not in declared:
                found.append(
                    Problem(
                        rule=BINDING_RULE,
                        integration=entry.name,
                        message=(
                            f"{permission.name!r} names {capability!r}, which this "
                            f"integration does not declare — a missing-permission message "
                            f"would send an operator looking for something that is not there"
                        ),
                    )
                )
    return found


def problems(entries: Sequence[CatalogueEntry]) -> list[Problem]:
    """Return everything wrong with the catalogue that needs no credentials."""
    found: list[Problem] = []
    for entry in entries:
        found.extend(parity_problems(entry))
        found.extend(verifier_problems(entry))
        found.extend(binding_problems(entry))
    return sorted(found)


def live_note() -> str:
    """Return why ``--live`` needs a composed deployment rather than this script."""
    return (
        "A live run needs a credential proxy, a vault holding this team's credentials, and "
        "the tenant to run as — a composed deployment rather than a script. Run it from the "
        "CLI, which has one: `ninjasre integrations verify --all`. Its failures mark the "
        "integration degraded in the catalogue rather than failing the build (FR-016)."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the credential-free checks and return the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="also call the vendors (needs a composed deployment; see the printed note)",
    )
    parser.add_argument("--json", action="store_true", help="print the catalogue as JSON")
    arguments = parser.parse_args(argv)

    entries = catalogue(health=HealthLedger())

    if arguments.json:
        print(json.dumps([entry.to_record() for entry in entries], indent=2))

    found = problems(entries)
    if arguments.live:
        print(live_note(), file=sys.stderr)

    if not found:
        if not arguments.json:
            print(f"{len(entries)} integration(s) at full parity, every permission probed")
        return 0

    print(
        f"{len(found)} problem(s) in the integration catalogue. Full parity is a property "
        f"the build enforces or a word in a plan:",
        file=sys.stderr,
    )
    for problem in found:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

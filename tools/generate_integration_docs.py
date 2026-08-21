"""Generate the integration catalogue page from the declarations themselves.

The same argument as the capability reference, and it gets stronger with every
vendor. A hand-written catalogue of every integration is a catalogue that
is wrong — not eventually, but at the first vendor whose permission list changes
and whose entry nobody remembers to update. A page saying an integration needs
one scope when it needs two is worse than no page: it sends an operator to grant
the wrong thing and then to disbelieve the error.

So this reads what the console reads: the same ``PROFILE`` declarations, the
same descriptors, the same parity reports. If the documentation and the
behaviour disagree, the documentation is stale by exactly one build.

Usage::

    python -m tools.generate_integration_docs [--output docs/integrations-catalogue.md]
                                              [--check]

``--check`` regenerates and compares without writing, which is what a build step
runs. Run as a module from the repository root; see
``tools/verify_integrations.py`` for why.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from integrations._catalogue.discovery import catalogue
from integrations._catalogue.entry import CatalogueEntry
from integrations._catalogue.gaps import gaps
from integrations._catalogue.validation import Artefact, artefacts, cost_of

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "integrations-catalogue.md"

_HEADER = """# Integration catalogue

Generated from the declarations by `tools/generate_integration_docs.py`. Do not
edit by hand — edit the integration and regenerate, or the two will disagree and
this file will be the one that is wrong.

Every integration ships the same seven artefacts. The build fails naming both
the integration and the artefact when one is missing, which is what makes "full
parity" a property rather than an aspiration.
"""


def _render_artefacts() -> list[str]:
    """Return the table of what each artefact prevents."""
    lines = ["## The seven artefacts", "", "| Artefact | Without it |", "|---|---|"]
    lines.extend(f"| `{artefact.value}` | {cost_of(artefact)} |" for artefact in artefacts())
    lines.append("")
    return lines


def _render_entry(entry: CatalogueEntry) -> list[str]:
    """Return the lines documenting one integration."""
    lines = [
        f"### `{entry.name}`",
        "",
        entry.summary,
        "",
        f"- **Category:** {entry.category.value}",
        f"- **Regions:** {', '.join(entry.regions)}",
        f"- **Credentials:** {', '.join(entry.required_credentials)}",
        f"- **SDK strategy:** `{entry.descriptor.sdk_strategy.value}`",
        f"- **Parity:** {entry.parity.status.value}",
        f"- **Health:** {entry.health.value}"
        + (f" — {entry.health_detail}" if entry.health_detail else ""),
    ]
    if entry.parity.missing:
        lines.append(
            "- **Missing:** " + ", ".join(artefact.value for artefact in entry.parity.missing)
        )
    if entry.capabilities:
        lines.extend(["", "**Capabilities:**", ""])
        lines.extend(f"- `{name}`" for name in entry.capabilities)
    if entry.profile.permissions:
        lines.extend(
            ["", "**Permissions:**", "", "| Permission | Grants | Without it |", "|---|---|---|"]
        )
        for permission in entry.profile.permissions:
            affected = ", ".join(f"`{name}`" for name in permission.capabilities) or "—"
            lines.append(f"| `{permission.name}` | {permission.grants} | {affected} |")
    if entry.profile.pagination:
        lines.extend(["", "**Pagination:**", ""])
        lines.extend(
            f"- `{endpoint.endpoint}` — {endpoint.style.value} on `{endpoint.parameter}`"
            for endpoint in entry.profile.pagination
        )
    lines.append("")
    return lines


def _render_gaps() -> list[str]:
    """Return the table of vendors the catalogue deliberately does not reach (FR-003)."""
    recorded = gaps()
    if not recorded:
        return []
    lines = [
        "## Recorded gaps",
        "",
        "A vendor nobody wrote is a vendor nobody is told about, so the omissions are a "
        "declaration rather than an absence. Each names why it cannot be built the way every "
        "other integration is, and what would have to change.",
        "",
    ]
    for gap in recorded:
        lines.extend(
            [
                f"### `{gap.integration}` — {gap.display_name}",
                "",
                f"- **Category:** {gap.category}",
                f"- **Why not:** {gap.reason}",
                f"- **What would change it:** {gap.what_would_change_it}",
                "",
            ]
        )
    return lines


def render(entries: Sequence[CatalogueEntry]) -> str:
    """Return the catalogue page for ``entries``."""
    complete = sum(1 for entry in entries if not entry.parity.missing)
    lines = [
        _HEADER,
        f"{len(entries)} integration(s), {complete} at full parity, "
        f"{len(gaps())} recorded as unreachable.",
        "",
    ]
    lines.extend(_render_artefacts())

    by_category: dict[str, list[CatalogueEntry]] = {}
    for entry in entries:
        by_category.setdefault(entry.category.value, []).append(entry)

    lines.extend(["## Integrations", ""])
    if not entries:
        lines.extend(["None installed.", ""])
    for category in sorted(by_category):
        lines.extend([f"### {category}", ""])
        for entry in by_category[category]:
            lines.extend(_render_entry(entry))

    lines.extend(_render_gaps())

    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the catalogue page, or report that it is out of date."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the written page differs from what the declarations produce",
    )
    arguments = parser.parse_args(argv)

    page = render(catalogue())

    if arguments.check:
        if not arguments.output.exists():
            print(f"{arguments.output} has not been generated", file=sys.stderr)
            return 1
        if arguments.output.read_text(encoding="utf-8") != page:
            print(
                f"{arguments.output} is out of date — run "
                "`python -m tools.generate_integration_docs`",
                file=sys.stderr,
            )
            return 1
        return 0

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {arguments.output.relative_to(REPO_ROOT)}")
    return 0


__all__ = ["Artefact", "render"]


if __name__ == "__main__":
    raise SystemExit(main())

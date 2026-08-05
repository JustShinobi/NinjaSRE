"""Generate the capability reference from the declarations themselves.

A hand-written reference for a catalogue this size is a reference that is
wrong. Not eventually — immediately, because the first tool whose side-effect
level changes is the first entry nobody remembers to update, and a reference
that says a tool is read-only when it is not is worse than no reference.

So the page is generated from the same metadata the scorer and the approval
gate read. If the documentation and the behaviour disagree, the documentation
is stale by exactly one build.

Usage::

    python tools/generate_capability_docs.py [--output docs/capabilities.md] [--check]

``--check`` regenerates and compares without writing, which is what a build
step would run.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from capabilities.registry.api import CapabilityView, catalogue_view, summary
from capabilities.registry.catalogue import build_registry
from core.capability.metadata import CapabilityKind, SideEffectLevel

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "capabilities.md"

_HEADER = """# Capability reference

Generated from the declarations by `tools/generate_capability_docs.py`. Do not
edit by hand — edit the capability and regenerate, or the two will disagree and
this file will be the one that is wrong.
"""

#: Rendered next to each level, because "write_reversible" does not tell a
#: reader what they are being asked to approve.
_LEVEL_NOTES: dict[str, str] = {
    SideEffectLevel.READ.value: "reads only",
    SideEffectLevel.READ_SENSITIVE.value: "reads data that may identify people",
    SideEffectLevel.WRITE_REVERSIBLE.value: "changes something, undoable by plan",
    SideEffectLevel.WRITE_IRREVERSIBLE.value: "changes something that cannot be undone",
    SideEffectLevel.DESTRUCTIVE.value: "destroys something",
}


def _render_tool(view: CapabilityView) -> list[str]:
    """Return the lines documenting one tool."""
    note = _LEVEL_NOTES.get(view.side_effect_level, "")
    lines = [
        f"#### `{view.name}`",
        "",
        view.description,
        "",
        f"- **Side effect:** `{view.side_effect_level}`" + (f" — {note}" if note else ""),
        f"- **Evidence:** {view.evidence_type} from {view.evidence_source}",
        f"- **Parallel safe:** {'yes' if view.parallel_safe else 'no'}",
    ]
    if view.requires:
        lines.append(f"- **Requires:** {', '.join(view.requires)}")
    if view.requires_approval:
        lines.append(f"- **Approval:** required — {view.approval_reason}")
    if view.use_cases:
        lines.extend(["", "**Use when:**", ""])
        lines.extend(f"- {entry}" for entry in view.use_cases)
    if view.anti_examples:
        lines.extend(["", "**Not for:**", ""])
        lines.extend(f"- {entry}" for entry in view.anti_examples)
    lines.append("")
    return lines


def _render_skill(view: CapabilityView) -> list[str]:
    """Return the lines documenting one skill."""
    lines = [f"### `{view.name}`", "", view.description, "", f"- **Domain:** {view.domain}"]
    if view.alert_sources:
        lines.append(f"- **Applies to alerts from:** {', '.join(view.alert_sources)}")
    if view.requires:
        lines.append(f"- **Requires:** {', '.join(view.requires)}")
    if view.directs_tools:
        lines.extend(["", "**Directs:**", ""])
        lines.extend(f"- `{name}`" for name in view.directs_tools)
    else:
        lines.extend(["", "Directs no tools — methodology only.", ""])
    lines.append("")
    return lines


def render(views: Sequence[CapabilityView]) -> str:
    """Return the reference page for ``views``."""
    counts = summary(views)
    lines = [
        _HEADER,
        f"{counts['tools']} tools and {counts['skills']} skills, "
        f"{counts['approval_gated']} of them approval-gated.",
        "",
        "## Skills",
        "",
    ]

    skills = [view for view in views if view.kind is CapabilityKind.SKILL]
    if skills:
        for view in skills:
            lines.extend(_render_skill(view))
    else:
        lines.extend(["None yet.", ""])

    lines.extend(["## Tools", ""])

    tools = [view for view in views if view.kind is CapabilityKind.TOOL]
    if tools:
        by_domain: dict[str, list[CapabilityView]] = {}
        for view in tools:
            by_domain.setdefault(view.domain or "uncategorised", []).append(view)
        for domain in sorted(by_domain):
            lines.extend([f"### {domain}", ""])
            for view in by_domain[domain]:
                lines.extend(_render_tool(view))
    else:
        lines.extend(["None yet.", ""])

    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the reference page, or report that it is out of date."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the written page differs from what the declarations produce",
    )
    arguments = parser.parse_args(argv)

    page = render(catalogue_view(build_registry()))

    if arguments.check:
        if not arguments.output.exists():
            print(f"{arguments.output} has not been generated", file=sys.stderr)
            return 1
        if arguments.output.read_text(encoding="utf-8") != page:
            print(
                f"{arguments.output} is out of date — run "
                "`python tools/generate_capability_docs.py`",
                file=sys.stderr,
            )
            return 1
        return 0

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {arguments.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""A deliberately small YAML reader for skill manifests.

Two reasons this is not a YAML library.

The first is dependencies: nothing in the runtime tree parses YAML today, and a
deployment that ships no vendor SDKs because it egresses nothing should not
acquire a parser to read seven keys out of a file the repository wrote itself.

The second is the one that actually matters. YAML is enormous, and most of it
is a liability in a file that eighty-five contributors will hand-write. Merge
keys, anchors, implicit typing that turns ``no`` into ``False`` and ``1.10``
into a float — every one of those is a manifest that parses successfully and
means something other than what its author wrote. This reader accepts scalars,
flat lists in either notation, and one level of nested mapping, and rejects
everything else by name. A manifest that would have surprised somebody fails
the build instead.

Strictness is uniform: duplicate keys, tab indentation, and unexpected nesting
are errors rather than resolutions.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What a frontmatter value can be after parsing. Everything is a string or a
#: list of strings — no implicit typing, so ``no`` stays ``"no"`` and a version
#: number stays a version number.
FrontmatterValue = str | list[str] | dict[str, "FrontmatterValue"]

#: Two spaces per level. One level of nesting is supported and that is all the
#: manifest format uses; anything deeper is a structure this reader would have
#: to guess at.
_INDENT = "  "

_MARKER = "---"


class FrontmatterError(Exception):
    """The frontmatter block cannot be read as written."""


@dataclass(frozen=True, slots=True)
class _Line:
    """One significant line, with its indentation already measured."""

    number: int
    depth: int
    text: str


def split_frontmatter(text: str, *, source: str) -> tuple[str, str]:
    """Return the frontmatter block and the body that follows it.

    A file with no frontmatter is an error rather than a skill with empty
    metadata: a skill nobody can find is indistinguishable from a skill that
    was never written, and the second at least fails loudly.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _MARKER:
        raise FrontmatterError(
            f"{source}: a skill manifest must open with a '---' frontmatter block"
        )

    for index in range(1, len(lines)):
        if lines[index].strip() == _MARKER:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :]).strip("\n")

    raise FrontmatterError(f"{source}: the frontmatter block is never closed with '---'")


def _significant_lines(block: str, *, source: str) -> list[_Line]:
    """Return the block's content lines, with comments and blanks dropped."""
    lines: list[_Line] = []

    for number, raw in enumerate(block.splitlines(), start=2):
        if "\t" in raw:
            raise FrontmatterError(
                f"{source}:{number}: indent with spaces — a tab's width is a matter of "
                "opinion, and a manifest that reads differently in two editors is worse "
                "than one that fails"
            )
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent % len(_INDENT):
            raise FrontmatterError(
                f"{source}:{number}: indent in multiples of two spaces, found {indent}"
            )
        lines.append(_Line(number=number, depth=indent // len(_INDENT), text=stripped))

    return lines


def _scalar(value: str) -> str:
    """Return a scalar with its optional quoting removed, and nothing else done."""
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in "\"'":
        return trimmed[1:-1]
    return trimmed


def _inline_list(value: str) -> list[str]:
    """Return the members of a ``[a, b, c]`` list."""
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    return [_scalar(member) for member in inner.split(",") if _scalar(member)]


def _parse_block(
    lines: list[_Line], index: int, depth: int, *, source: str
) -> tuple[dict[str, FrontmatterValue], int]:
    """Return the mapping at ``depth`` starting at ``index``, and where it ended."""
    mapping: dict[str, FrontmatterValue] = {}

    while index < len(lines):
        line = lines[index]
        if line.depth < depth:
            break
        if line.depth > depth:
            raise FrontmatterError(
                f"{source}:{line.number}: unexpected indentation — this reader supports "
                "one level of nesting"
            )
        if line.text.startswith("- "):
            raise FrontmatterError(f"{source}:{line.number}: a list item needs a key above it")

        key, separator, remainder = line.text.partition(":")
        if not separator:
            raise FrontmatterError(f"{source}:{line.number}: expected 'key: value'")

        key = key.strip()
        if key in mapping:
            raise FrontmatterError(
                f"{source}:{line.number}: duplicate key {key!r} — one of the two was "
                "going to be silently discarded"
            )

        remainder = remainder.strip()
        index += 1

        if remainder.startswith("[") and remainder.endswith("]"):
            mapping[key] = _inline_list(remainder)
            continue
        if remainder:
            mapping[key] = _scalar(remainder)
            continue

        # A bare `key:` introduces either a block list or a nested mapping, and
        # which one is decided by the first line under it.
        if index < len(lines) and lines[index].depth == depth + 1:
            if lines[index].text.startswith("- "):
                members: list[str] = []
                while (
                    index < len(lines)
                    and lines[index].depth == depth + 1
                    and lines[index].text.startswith("- ")
                ):
                    members.append(_scalar(lines[index].text[2:]))
                    index += 1
                mapping[key] = members
            else:
                nested, index = _parse_block(lines, index, depth + 1, source=source)
                mapping[key] = nested
            continue

        mapping[key] = ""

    return mapping, index


def parse_frontmatter(block: str, *, source: str) -> dict[str, FrontmatterValue]:
    """Return the mapping a frontmatter block describes."""
    lines = _significant_lines(block, source=source)
    mapping, consumed = _parse_block(lines, 0, 0, source=source)

    if consumed != len(lines):
        raise FrontmatterError(f"{source}:{lines[consumed].number}: could not be read")

    return mapping


def as_list(value: FrontmatterValue | None, *, key: str, source: str) -> tuple[str, ...]:
    """Return ``value`` as a tuple of strings, whichever notation wrote it."""
    if value is None or value == "":
        return ()
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, str):
        # A single entry written without brackets. Common enough in a
        # hand-written file that rejecting it would be pedantry.
        return (value,)
    raise FrontmatterError(f"{source}: {key} must be a list, not a nested mapping")


def as_text(value: FrontmatterValue | None, *, key: str, source: str) -> str:
    """Return ``value`` as a scalar string, or explain what it was instead."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise FrontmatterError(f"{source}: {key} must be a single value, not a list or mapping")


def as_mapping(
    value: FrontmatterValue | None, *, key: str, source: str
) -> dict[str, FrontmatterValue]:
    """Return ``value`` as a nested mapping, or explain what it was instead."""
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    raise FrontmatterError(f"{source}: {key} must be a mapping of named lists")


__all__ = [
    "FrontmatterError",
    "FrontmatterValue",
    "as_list",
    "as_mapping",
    "as_text",
    "parse_frontmatter",
    "split_frontmatter",
]

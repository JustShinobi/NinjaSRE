"""The machine-readable half of every command: one envelope, one shape.

A script that automates around the CLI reads the same five keys from every
command — which is what makes "parse the output of ``ninjasre``" a thing an
operator can write once. The command's own payload sits under ``data``, and the
identifier under ``schema`` says which published document describes it, so a
script can refuse a version it does not understand rather than misreading one.

The envelope is emitted for failures too. A command that printed a JSON object
on success and a bare error line on failure would make every caller parse two
formats, and the one they get wrong is the failure path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from surfaces.cli.output.schemas import COMMAND_SCHEMAS, ENVELOPE_SCHEMA, schema_id, validate


@dataclass(frozen=True, slots=True)
class Envelope:
    """One command's output, in the shape every command shares."""

    command: str
    data: Mapping[str, Any] = field(default_factory=dict)
    ok: bool = True
    errors: tuple[str, ...] = ()

    @property
    def schema(self) -> str:
        """Return the identifier of the document describing this payload."""
        return schema_id(self.command)

    def to_record(self) -> dict[str, Any]:
        """Return this envelope as a JSON-serialisable document."""
        return {
            "schema": self.schema,
            "command": self.command,
            "ok": self.ok,
            "data": dict(self.data),
            "errors": list(self.errors),
        }

    def validated(self) -> dict[str, Any]:
        """Return this envelope's document, checked against its schema.

        A failure envelope is checked against the envelope schema alone. Its
        ``data`` is empty by construction, and holding it to the success shape
        would mean a command could not report an error without first producing
        the payload it failed to produce.

        Raises:
            ValueError: the document diverges from what is published.
            KeyError: nothing is published for this command.
        """
        record = self.to_record()
        if not self.ok:
            validate(record, ENVELOPE_SCHEMA)
            return record

        validate(record, ENVELOPE_SCHEMA)
        validate(record["data"], COMMAND_SCHEMAS[self.command])
        return record


def failure(command: str, *errors: str) -> Envelope:
    """Return the envelope a failed command emits."""
    return Envelope(command=command, ok=False, errors=tuple(errors))


def render(envelope: Envelope, *, indent: int | None = 2) -> str:
    """Return ``envelope`` as one JSON document.

    Indented by default because the reader is as often a person running the
    command with ``--json`` to see the shape as it is a script — and ``jq`` does
    not mind either way. ``indent=None`` gives the compact form for a log.
    """
    return json.dumps(
        envelope.validated(),
        indent=indent,
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )


def envelope_of(command: str, data: Mapping[str, Any], *, warnings: Sequence[str] = ()) -> Envelope:
    """Return a successful envelope carrying ``data``.

    Warnings ride in ``errors`` with ``ok`` still true. A command that
    succeeded with a caveat has one thing to say, and a second key nobody reads
    is how the caveat gets lost.
    """
    return Envelope(command=command, data=data, ok=True, errors=tuple(warnings))


__all__ = [
    "Envelope",
    "envelope_of",
    "failure",
    "render",
]

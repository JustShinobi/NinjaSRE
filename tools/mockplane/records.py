"""What one captured answer is, and how it says where it came from.

Every record in this dataset states how it was obtained. That is not
bookkeeping. Half of what the console shows is served by nothing yet, so half of
these records are *projections* — a shape assembled from a direct read of the
cluster, aimed at an endpoint that does not exist. A projection that could be
read as a recording of a live gateway is a fixture somebody will one day trust
as evidence that the endpoint worked.

The three classes stay distinguishable from each other too, not just from the
gateway. When the Proxmox work lands, the ``pvesh`` records come from the
gateway instead and that half of the direct path is deleted; the shell records
have no gateway equivalent and stay. Telling them apart is what makes that a
change somebody can make rather than a change somebody has to reconstruct.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

#: The contract version a capture was taken under. Recorded on every record so a
#: fixture set produced before a breaking change can be told from one after it.
CONTRACT_VERSION: Final = "1.0.0"


class Provenance(StrEnum):
    """How one record was obtained."""

    #: A live NinjaSRE deployment answered the request. The record is a
    #: recording, and the endpoint it belongs to exists today.
    GATEWAY = "gateway"

    #: ``pvesh ... --output-format json`` on a cluster node. The same API the
    #: cluster's REST endpoint serves, so this payload is what the integration's
    #: client will return once it exists — which is what makes it reusable
    #: rather than throwaway.
    PVESH = "pvesh"

    #: A shell read the API cannot answer: failed units, thin-pool metadata,
    #: the corosync configuration as written, mount state, boot history. There
    #: is no future endpoint that makes these redundant.
    SHELL = "shell"

    @property
    def is_projected(self) -> bool:
        """Return whether a record from this source was shaped rather than served."""
        return self is not Provenance.GATEWAY


@dataclass(frozen=True, slots=True)
class Request:
    """The request that produced a record, in whichever vocabulary made it.

    A gateway request has a method and a path. A direct read has a command and
    the node it ran on. Both are recorded, because "what did you ask" is the
    first question anybody has about a fixture that looks wrong.
    """

    method: str = ""
    path: str = ""
    query: Mapping[str, str] = field(default_factory=dict)
    command: str = ""
    node: str = ""

    def as_json(self) -> dict[str, Any]:
        """Return this request as the object a capture file holds."""
        return {
            "method": self.method,
            "path": self.path,
            "query": dict(self.query),
            "command": self.command,
            "node": self.node,
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> Request:
        """Return the request a capture file's object describes."""
        query = document.get("query")
        return cls(
            method=str(document.get("method", "")),
            path=str(document.get("path", "")),
            query={str(k): str(v) for k, v in query.items()} if isinstance(query, dict) else {},
            command=str(document.get("command", "")),
            node=str(document.get("node", "")),
        )


@dataclass(frozen=True, slots=True)
class CapturedRecord:
    """One answer, everything that produced it, and where it came from."""

    #: The catalogue slug of the endpoint this record answers.
    slug: str
    #: The variables the request bound, so a templated endpoint can hold many.
    arguments: Mapping[str, str]
    status: int
    body: Any
    provenance: Provenance
    request: Request
    contract_version: str = CONTRACT_VERSION

    @property
    def is_projected(self) -> bool:
        """Return whether this record was shaped for an endpoint nothing serves."""
        return self.provenance.is_projected

    def with_body(self, body: Any) -> CapturedRecord:
        """Return this record carrying ``body`` instead."""
        return CapturedRecord(
            slug=self.slug,
            arguments=self.arguments,
            status=self.status,
            body=body,
            provenance=self.provenance,
            request=self.request,
            contract_version=self.contract_version,
        )

    def as_json(self) -> dict[str, Any]:
        """Return this record as the object a capture or fixture file holds."""
        return {
            "slug": self.slug,
            "arguments": dict(self.arguments),
            "status": self.status,
            "provenance": self.provenance.value,
            "contract_version": self.contract_version,
            "request": self.request.as_json(),
            "body": self.body,
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> CapturedRecord:
        """Return the record a capture or fixture file's object describes.

        Raises:
            ValueError: the object names a provenance that does not exist, which
                is how a hand-edited fixture stops being attributable.
        """
        raw = str(document.get("provenance", ""))
        try:
            provenance = Provenance(raw)
        except ValueError as error:
            raise ValueError(
                f"{raw!r} is not a source a record can come from; "
                f"it must be one of {', '.join(p.value for p in Provenance)}"
            ) from error
        arguments = document.get("arguments")
        return cls(
            slug=str(document["slug"]),
            arguments=(
                {str(k): str(v) for k, v in arguments.items()}
                if isinstance(arguments, dict)
                else {}
            ),
            status=int(document.get("status", 200)),
            body=document.get("body"),
            provenance=provenance,
            request=Request.from_json(document.get("request", {}) or {}),
            contract_version=str(document.get("contract_version", CONTRACT_VERSION)),
        )


def dumps(document: Any) -> str:
    """Return ``document`` as the canonical JSON this dataset is written in.

    Sorted keys, two-space indent, a trailing newline. Byte-identical output on
    a second run is a requirement rather than a nicety: a visual-regression
    baseline captured against a dataset that reorders its keys is a baseline
    that fails on the next commit for no reason anybody changed.
    """
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


__all__ = [
    "CONTRACT_VERSION",
    "CapturedRecord",
    "Provenance",
    "Request",
    "dumps",
]

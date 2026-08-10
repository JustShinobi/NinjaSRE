"""Offering the integrations the estate has already shown are there.

Discovery runs before the integrations step of the wizard, and it is the reason
the steps are in that order. Once it has run, the deployment knows something the
catalogue does not: one of the fifty-seven containers is called ``prometheus``
and sits on ``10.20.20.37``. Offering that entry first, with the address filled
in, turns "find the right vendor among ninety and go and look up where it runs"
into "paste a token".

**The derivation lives here rather than in a surface.** Both the console wizard
and the CLI wizard ask the same question, and a rule implemented twice is the
two-answers failure the constitution keeps warning about — one screen offering
Prometheus first while the other buries it, with nobody able to say which is
right. Serving the suggestion from the catalogue response means both get it for
free.

**Matching is exact and total.** A resource's display name or one of its labels
is the integration's own name, or there is no match. No scoring, no fuzzy
distance, and no model: the value of a prefilled address is that an operator can
accept it without checking, and the moment it might be wrong they have to check
every one — which costs more than the alphabet did.

A resource that matches nothing produces nothing and the catalogue keeps its
order. That is the ordinary case and it must stay cheap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from platform.estate.signal_map import ADDRESS_ATTRIBUTE
from platform.persistence.ports.estate_repository import Resource

#: What a suggested endpoint is spelled with. Plain HTTP, because a self-hosted
#: exporter on a private network usually is — and because an operator correcting
#: a scheme is doing a second's work, whereas an operator discovering an address
#: is doing an afternoon's.
SUGGESTED_SCHEME: Final = "http"


@dataclass(frozen=True, slots=True)
class Suggestion:
    """One integration the estate says is already running, and where.

    ``because`` is the sentence that makes the address checkable. An endpoint
    that appeared in a form with no provenance is one the operator has to go and
    verify, which is the saving spent.
    """

    integration: str
    address: str
    from_resource: str
    because: str

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form a catalogue response carries."""
        return {
            "integration": self.integration,
            "address": self.address,
            "from_resource": self.from_resource,
            "because": self.because,
        }


def suggest_integrations(
    resources: Iterable[Resource], *, offers: Mapping[str, int]
) -> tuple[Suggestion, ...]:
    """Return the integrations this estate makes obvious, in integration-name order.

    ``offers`` is the catalogue: every integration this deployment could
    configure, mapped to the port a default install of it listens on. A vendor
    with no such port — anything hosted, which is most of the catalogue — is
    never suggested from a local address, because a container somebody called
    ``datadog`` is not a Datadog endpoint and offering one would be putting a
    wrong answer at the top of the list.

    Order is by integration name rather than by discovery order. Two sweeps of
    one cluster return resources in whatever order the provider listed them, and
    a wizard whose entries move between renders is a wizard nobody trusts.
    """
    found: dict[str, Suggestion] = {}
    for resource in resources:
        address = str(dict(resource.attributes).get(ADDRESS_ATTRIBUTE, "") or "")
        if not address:
            continue
        for name in _names_of(resource):
            port = offers.get(name, 0)
            if port <= 0 or name in found:
                continue
            found[name] = Suggestion(
                integration=name,
                address=f"{SUGGESTED_SCHEME}://{address}:{port}",
                from_resource=resource.resource_id,
                because=(
                    f"this estate holds a {resource.kind} called "
                    f"{resource.display_name or resource.resource_id!r} at {address}, which is "
                    f"where {name} was found rather than where anyone guessed it would be"
                ),
            )
    return tuple(found[name] for name in sorted(found))


def _names_of(resource: Resource) -> tuple[str, ...]:
    """Return the exact strings this resource may be matched on.

    The display name and the labels, lower-cased, and nothing derived from
    either. A substring rule would match ``prometheus-backup``, which is a
    backup *of* Prometheus and would put its address in the endpoint box.
    """
    return tuple(
        {
            resource.display_name.strip().lower(),
            *(label.strip().lower() for label in resource.labels),
        }
        - {""}
    )


__all__ = ["SUGGESTED_SCHEME", "Suggestion", "suggest_integrations"]

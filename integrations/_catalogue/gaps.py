"""The vendors this catalogue does not cover, recorded rather than omitted (FR-003).

The parity check walks the packages that exist. That is the right design and it
has one blind spot: a vendor nobody wrote is a vendor nobody is told about, and
the catalogue reports full parity for everything it can see. An operator
evaluating NinjaSRE against their stack then discovers the absence by looking
for it, which is the worst moment and the worst way.

So the omissions are a declaration. Each names the vendor, why it cannot be
built the way every other integration is, and what would have to change — which
is the part that turns "we did not do it" into something a reader can weigh.

**Gaps have two causes, and telling them apart is the point.** One kind cannot
be built the way every other integration is; the other could be and was decided
against. Both are recorded and both carry what would change the decision, but an
operator reading "the credential proxy is HTTP and this speaks a binary wire
protocol" and one reading "two other sources already answer this question" are
being told different things, and a single list would flatten them into "not
supported".

**The first cause is architectural.** Article IV puts the credential at the network edge, in an HTTP
proxy: a client sends an unauthenticated request and the proxy attaches the
secret. A vendor that speaks a binary wire protocol has no request for the proxy
to attach anything to. There are exactly two ways to build such a client, and
both are refused: hold the credential in the process, which Article IV forbids
outright, or open the connection from somewhere that holds it, which is the same
thing with more steps.

The managed and HTTP-fronted forms of these systems *are* in the catalogue, and
the entry below says which — `aws_rds` for a managed PostgreSQL or MySQL,
`mongodb_atlas` for a hosted MongoDB, `clickhouse` for the one database whose
first-class interface is HTTP. What is missing is the self-hosted engine on its
own port, and saying so precisely is more useful than saying "databases are not
supported".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class GapCause(StrEnum):
    """Why a vendor is not in the catalogue."""

    #: It cannot be built the way every other integration is. Article IV puts
    #: the credential in an HTTP proxy, and this vendor has no HTTP request for
    #: the proxy to attach a secret to.
    UNREACHABLE = "unreachable"

    #: It could be built and was decided against, with the reasoning recorded.
    #: A decision is different from an impossibility: this one is reopened by a
    #: change in circumstances rather than by a change in the architecture.
    NOT_BUILT = "not_built"


@dataclass(frozen=True, slots=True)
class CatalogueGap:
    """One vendor the catalogue does not cover, and why."""

    integration: str
    display_name: str
    category: str
    reason: str
    what_would_change_it: str
    cause: GapCause = GapCause.UNREACHABLE

    def __post_init__(self) -> None:
        if not self.reason.strip() or not self.what_would_change_it.strip():
            raise ValueError(
                f"{self.integration}: a gap with no reason or no resolution is an omission "
                f"with a schema around it, which is what this module exists to prevent"
            )

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form the console and the docs render."""
        return {
            "integration": self.integration,
            "display_name": self.display_name,
            "category": self.category,
            "cause": self.cause.value,
            "reason": self.reason,
            "resolution": self.what_would_change_it,
        }


#: What a credential proxy that speaks only HTTP cannot reach, said once.
_WIRE_PROTOCOL: Final = (
    "The server speaks its own binary wire protocol on its own port. The credential proxy is "
    "HTTP: it attaches a secret to a request, and there is no request here to attach one to. "
    "Building the client anyway would mean holding the credential in the agent's process, "
    "which Article IV forbids outright."
)

UNREACHABLE: Final[tuple[CatalogueGap, ...]] = (
    CatalogueGap(
        integration="postgresql",
        display_name="PostgreSQL",
        category="database",
        reason=_WIRE_PROTOCOL,
        what_would_change_it=(
            "A protocol bridge that terminates the credential outside the agent process, the "
            "way the HTTP proxy does. Nothing in the catalogue reaches a managed PostgreSQL's "
            "control plane today."
        ),
    ),
    CatalogueGap(
        integration="mysql",
        display_name="MySQL",
        category="database",
        reason=_WIRE_PROTOCOL,
        what_would_change_it=(
            "The same bridge PostgreSQL needs. Nothing in the catalogue reaches a managed "
            "MySQL's control plane today."
        ),
    ),
    CatalogueGap(
        integration="mariadb",
        display_name="MariaDB",
        category="database",
        reason=_WIRE_PROTOCOL,
        what_would_change_it=(
            "The same bridge MySQL needs — MariaDB speaks the MySQL protocol and has the same "
            "constraint for the same reason."
        ),
    ),
    CatalogueGap(
        integration="mongodb",
        display_name="MongoDB",
        category="database",
        reason=_WIRE_PROTOCOL,
        what_would_change_it=(
            "A protocol bridge. Nothing in the catalogue reaches a hosted deployment's "
            "administration API today, and a self-hosted replica set on port 27017 has no "
            "equivalent either way."
        ),
    ),
    CatalogueGap(
        integration="redis_server",
        display_name="Redis (self-hosted)",
        category="database",
        reason=_WIRE_PROTOCOL,
        what_would_change_it=(
            "A protocol bridge. `redis` is in the catalogue and reads Redis Cloud's control "
            "plane over HTTP; the keyspace, the slow log, and `INFO` on a self-hosted server "
            "are RESP and are not reachable."
        ),
    ),
    CatalogueGap(
        integration="smtp",
        display_name="SMTP",
        category="communication",
        reason=(
            "SMTP is a stateful line protocol over its own port, not a request-response API. "
            "The credential proxy attaches a secret to an HTTP request; an SMTP session has "
            "no such request, and authentication happens inside a conversation the proxy "
            "cannot participate in."
        ),
        what_would_change_it=(
            "Either a protocol bridge that terminates the SMTP credential outside the agent "
            "process, or delivery through a vendor with an HTTP API — `pushover` is in the "
            "catalogue and reaches a person without an SMTP session."
        ),
    ),
    CatalogueGap(
        integration="helm",
        display_name="Helm",
        category="cicd",
        reason=(
            "Helm 3 has no server component. A release is a Secret in the cluster and the CLI "
            "is what reads it, so there is no API for an integration to hold a credential "
            "against — the credential that matters is the cluster's."
        ),
        what_would_change_it=(
            "Nothing about Helm. Release history is already reachable: `kubernetes` reads the "
            "release Secrets in a namespace, and `argocd` answers the same question for the "
            "estates that deploy charts through it."
        ),
    ),
)


#: The vendors this deployment could reach and does not, with the reasoning.
#:
#: The distinction from ``UNREACHABLE`` is worth keeping: nothing about the
#: architecture stops either of these being built, and both would be a week's
#: work. They are absent because somebody weighed them and wrote down what they
#: decided — which is what makes "should we build X" a conversation that starts
#: from an argument rather than from scratch.
NOT_BUILT: Final[tuple[CatalogueGap, ...]] = (
    CatalogueGap(
        integration="gatus",
        display_name="Gatus",
        category="observability",
        cause=GapCause.NOT_BUILT,
        reason=(
            "Gatus answers one question — is this endpoint responding — and two configured "
            "sources already answer it by different routes: the hypervisor reports each "
            "guest's own state, and a blackbox exporter reports reachability from outside, "
            "both reaching the platform through Prometheus. A third path to the same answer "
            "is a third thing to keep credentials for and no new signal, and an "
            "investigation offered three sources for one question spends turns choosing "
            "between them."
        ),
        what_would_change_it=(
            "A synthetic check that asserts something neither of the other two can — a login "
            "flow, a certificate chain, a response body — or an estate where Gatus is the "
            "only thing watching a class of endpoint the hypervisor cannot see."
        ),
    ),
    CatalogueGap(
        integration="netbox",
        display_name="NetBox",
        category="infrastructure",
        cause=GapCause.NOT_BUILT,
        reason=(
            "NetBox is a source of truth for network and addressing, and both already reach "
            "the platform: the addressing comes from the hypervisor with each guest, and the "
            "zones come from the declared inventory the estate is reconciled against. "
            "Ingesting the same facts from a third place is a third answer to 'which network "
            "is this on', and the failure that produces is two of them disagreeing quietly."
        ),
        what_would_change_it=(
            "An estate that grows past what the repository's own inventory describes — "
            "hardware, circuits, addressing NetBox is the only record of — at which point it "
            "stops being a duplicate and becomes the source for facts nothing else holds."
        ),
    ),
)


def gaps() -> tuple[CatalogueGap, ...]:
    """Return every vendor this catalogue does not cover, in declaration order."""
    return UNREACHABLE + NOT_BUILT


def unreachable() -> tuple[CatalogueGap, ...]:
    """Return the vendors the architecture cannot reach."""
    return UNREACHABLE


def not_built() -> tuple[CatalogueGap, ...]:
    """Return the vendors that were weighed and decided against."""
    return NOT_BUILT


def gap_for(integration: str) -> CatalogueGap | None:
    """Return the recorded gap for ``integration``, or ``None`` when there is none."""
    for gap in gaps():
        if gap.integration == integration:
            return gap
    return None


def is_recorded(integration: str) -> bool:
    """Return whether ``integration`` is a recorded gap rather than an unnoticed absence."""
    return gap_for(integration) is not None


__all__ = [
    "NOT_BUILT",
    "UNREACHABLE",
    "CatalogueGap",
    "GapCause",
    "gap_for",
    "gaps",
    "is_recorded",
    "not_built",
    "unreachable",
]

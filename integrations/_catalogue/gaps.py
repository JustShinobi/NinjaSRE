"""The vendors that cannot reach parity, recorded rather than omitted (FR-003).

The parity check walks the packages that exist. That is the right design and it
has one blind spot: a vendor nobody wrote is a vendor nobody is told about, and
the catalogue reports full parity for everything it can see. An operator
evaluating NinjaSRE against their stack then discovers the absence by looking
for it, which is the worst moment and the worst way.

So the omissions are a declaration. Each names the vendor, why it cannot be
built the way every other integration is, and what would have to change — which
is the part that turns "we did not do it" into something a reader can weigh.

**Every gap here has the same cause**, and it is architectural rather than a
matter of effort. Article IV puts the credential at the network edge, in an HTTP
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
from typing import Final


@dataclass(frozen=True, slots=True)
class CatalogueGap:
    """One vendor the catalogue does not reach, and why."""

    integration: str
    display_name: str
    category: str
    reason: str
    what_would_change_it: str

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
            "way the HTTP proxy does. Until there is one, a managed PostgreSQL is reachable "
            "through its cloud control plane — `aws_rds` for RDS and Aurora, `supabase` for "
            "Supabase — which answers instance state, failovers, and parameter changes but "
            "not sessions or query plans."
        ),
    ),
    CatalogueGap(
        integration="mysql",
        display_name="MySQL",
        category="database",
        reason=_WIRE_PROTOCOL,
        what_would_change_it=(
            "The same bridge PostgreSQL needs. A managed MySQL is reachable through "
            "`aws_rds`, which answers instance state and the event history and not what is "
            "executing inside the engine."
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
            "A protocol bridge, or Atlas: `mongodb_atlas` reaches a hosted deployment through "
            "the Atlas administration API and answers process and cluster state. A "
            "self-hosted replica set on port 27017 has no equivalent."
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
            "process, or delivery through a vendor with an HTTP API — `twilio` and `pushover` "
            "are both in the catalogue and reach a person without an SMTP session."
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


def gaps() -> tuple[CatalogueGap, ...]:
    """Return every vendor the catalogue records as unreachable, in declaration order."""
    return UNREACHABLE


def gap_for(integration: str) -> CatalogueGap | None:
    """Return the recorded gap for ``integration``, or ``None`` when there is none."""
    for gap in UNREACHABLE:
        if gap.integration == integration:
            return gap
    return None


def is_recorded(integration: str) -> bool:
    """Return whether ``integration`` is a recorded gap rather than an unnoticed absence."""
    return gap_for(integration) is not None


__all__ = [
    "UNREACHABLE",
    "CatalogueGap",
    "gap_for",
    "gaps",
    "is_recorded",
]

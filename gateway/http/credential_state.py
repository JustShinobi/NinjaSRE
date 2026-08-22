"""What "configured" means for a vendor that asks for no credential.

The vault answers one question — is a credential present, current, decryptable —
and for most of the catalogue that is the whole story. For a self-hosted vendor
that ships no authentication it is the wrong question: Alertmanager, Prometheus
and Loki are reached by being told where they are, nothing goes into the vault,
and the honest vault answer ("nothing is stored") is not the answer to "is this
connected".

Two routes need that translation — the write and the verify beside it — and they
had it in one place only. The write route compensated inline; the verify route
did not, so saving an address reported success and pressing "Test again"
immediately afterwards reported failure, wrote the failure down, and degraded
the card for good. One function, used by both, is what stops them drifting
again.

**The relaxation is for absence, and only where there is an address.** A vendor
nobody has pointed anywhere has nothing to reach, so "missing" is exactly right
there. A credential that is present and expired is present and expired: calling
it configured would hide the one state an operator has to act on.
"""

from __future__ import annotations

from platform.credentials.health import CredentialHealthState
from platform.credentials.schemas import CredentialSchema


def _vault_requires_nothing(schema: CredentialSchema) -> bool:
    """Return whether this vendor can be complete with an empty vault.

    ``for_vault`` returns ``None`` for a schema that is all address and no
    credential — there is nothing the vault could ever hold for it. Reading that
    as "fall back to the whole schema" is how the rule silently stops firing,
    because the whole schema's required fields include the address that went
    somewhere else entirely.
    """
    stored = schema.for_vault()
    return stored is None or not stored.required_names


def effective_credential_state(
    state: CredentialHealthState,
    *,
    schema: CredentialSchema,
    addressed: bool,
) -> CredentialHealthState:
    """Return what ``state`` means for this vendor, given whether it has an address.

    Only ``MISSING`` is ever rewritten, and only for a vendor whose vault half
    requires nothing and which an operator has pointed somewhere. Everything
    else is returned untouched, because everything else is a fact about a
    credential that exists.
    """
    if state is not CredentialHealthState.MISSING:
        return state
    if not addressed or not _vault_requires_nothing(schema):
        return state
    return CredentialHealthState.CONFIGURED


def credential_detail(state: CredentialHealthState, *, address_only: bool = False) -> str:
    """Return the sentence a recorded check carries, for each credential state.

    Written here rather than taken from the enum because the record is read by a
    person: "undecryptable" is a state name, and "the stored credential cannot
    be decrypted with this deployment's key" is something somebody can act on.

    ``address_only`` is the case this module exists for. "The stored credential
    is present and current" would be a false sentence about a vendor that stores
    none, and an operator reading the ledger six months later would go looking
    for a credential nobody ever entered.
    """
    if address_only and state is CredentialHealthState.CONFIGURED:
        return (
            "this vendor needs no credential of its own; it is configured by the "
            "address it was pointed at"
        )
    return {
        CredentialHealthState.CONFIGURED: "the stored credential is present and current",
        CredentialHealthState.MISSING: "no credential is stored for this integration",
        CredentialHealthState.EXPIRED: "the stored credential has expired",
        CredentialHealthState.UNDECRYPTABLE: (
            "the stored credential cannot be decrypted with this deployment's key"
        ),
    }[state]


__all__ = ["credential_detail", "effective_credential_state"]

"""Where a vendor is, kept where the proxy already looks for it.

A credential form now asks two different kinds of question. "What is the token"
is a credential, and it goes to the vault, which has no read-back and never
will. "Where is your Alertmanager" is not a credential at all — it is public,
it is readable, it belongs in a diagnostic, and the one thing that must be able
to read it is the process that decides whether a call is permitted to leave.

That process already reads it. ``gateway/proxy/hosts.py`` builds the egress
allow-list from ``integrations.active[].base_url`` in the configuration tree,
with provenance, a preview and an audit row behind every change. What was
missing was anything that wrote there: the field was declared, documented as
"the address of your own instance", and reachable only by hand-editing a
configuration document nobody knew to edit.

So this module is the short path between the form and that field. It splits a
submitted credential by where each half belongs, upserts the address, and reads
the addresses back for whoever is composing a client. Nothing here holds or
touches a secret: ``split_by_destination`` returns the secret half untouched to
its caller and never inspects it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from platform.config_service.schema.integrations import CertificateTrustSettings
from platform.config_service.service import ConfigService
from platform.credentials.proxy.trust import CertificateTrust, TrustAnchor
from platform.credentials.schemas import CredentialSchema
from platform.identity.permissions import Permission
from platform.observability.logging import get_logger
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.transaction import TenantScope

logger = get_logger(__name__)

#: The configuration path an integration entry lives under. Spelled once here
#: rather than at each call site, because a patch built against the wrong path
#: validates cleanly and writes nothing an integration will ever read.
ACTIVE_PATH = ("integrations", "active")


def split_by_destination(
    schema: CredentialSchema, values: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``values`` split into what the vault holds and what configuration holds.

    Keyed by the schema's own declaration rather than by field name, so an
    integration that calls its address something other than ``endpoint`` is
    routed correctly without this module knowing the name. A value the schema
    does not declare stays on the vault side, where the schema's own validation
    is what refuses it — refusing it here would be a second, quieter rejection
    with a worse message.
    """
    addresses = set(schema.endpoint_names)
    vault = {name: value for name, value in values.items() if name not in addresses}
    configured = {name: value for name, value in values.items() if name in addresses}
    return vault, configured


def _entry_records(active: Any) -> list[dict[str, Any]]:
    """Return the active integration entries as plain documents a patch can carry."""
    records: list[dict[str, Any]] = []
    for entry in active:
        record: dict[str, Any] = {"name": entry.name, "enabled": entry.enabled}
        for field_name in ("credential", "region", "site", "base_url"):
            value = getattr(entry, field_name, None)
            if value:
                record[field_name] = value
        settings = dict(getattr(entry, "settings", {}) or {})
        if settings:
            record["settings"] = settings
        # The certificate trust, carried like everything else. This copy is a
        # fixed set of fields, and a field outside it is erased by the first
        # save afterwards — so an operator who declared a fingerprint and then
        # corrected the address would silently lose the declaration, and the
        # symptom would be every call failing verification for no visible
        # reason.
        declared = _trust_document(entry)
        if declared:
            record["trust"] = declared
        records.append(record)
    return records


def _trust_document(entry: Any) -> dict[str, Any]:
    """Return an entry's certificate-trust section as a plain document."""
    declared = getattr(entry, "trust", None)
    if declared is None:
        return {}
    if isinstance(declared, Mapping):
        return {name: value for name, value in declared.items() if value not in (None, (), [])}
    dumped = getattr(declared, "model_dump", None)
    if dumped is None:
        return {}
    written = dumped(exclude_none=True)
    return {name: value for name, value in written.items() if value not in ((), [])}


class Permits(Protocol):
    """Whatever answers "may this principal do that", as the guard asks it."""

    def require(self, permission: Permission, *, node_id: str | None = None) -> None:
        """Raise ``PermissionDenied`` unless the principal holds ``permission``."""


@dataclass(frozen=True, slots=True)
class StampedTrust:
    """A declaration as the server will write it, with the client's identity removed.

    Constructed only through :func:`stamped_trust`, so there is one place where
    "who accepted this" is decided and it is never the request body. The value
    validates on construction, which is what makes the permission check below
    the *only* thing standing between a well-formed declaration and the
    document — a refusal cannot leave a half-written entry because nothing is
    written until both have passed.
    """

    section: CertificateTrustSettings

    @property
    def anchor(self) -> TrustAnchor:
        """Return which of the four forms this is."""
        return self.section.declaration().anchor

    def anchor_is(self, anchor: TrustAnchor) -> bool:
        """Return whether this declaration is ``anchor``."""
        return self.anchor is anchor

    @property
    def unverified_accepted_by(self) -> str:
        """Return the authenticated identity that accepted it, or empty."""
        return self.section.unverified_accepted_by or ""

    @property
    def unverified_accepted_at(self) -> str:
        """Return the server instant it was accepted at, or empty."""
        return self.section.unverified_accepted_at or ""

    def declaration(self, *addresses: str) -> CertificateTrust:
        """Return this as the value the proxy's egress applies."""
        return self.section.declaration(*addresses)

    def document(self) -> dict[str, Any]:
        """Return the plain document written into the integration entry."""
        written = self.section.model_dump(exclude_none=True)
        return {name: value for name, value in written.items() if value not in ((), [])}

    def refuse_unless_permitted(self, permissions: Permits, *, node_id: str | None = None) -> None:
        """Raise unless the caller may declare *this* form of trust.

        Pinning a fingerprint and supplying an authority narrow the anchor
        rather than widening it, so they need only what writing an address
        already needs. Accepting an unverified certificate gives up a guarantee
        and returns nothing but convenience, and it needs the permission that
        exists to be distinguishable from editing configuration.
        """
        permissions.require(Permission.INTEGRATION_MANAGE, node_id=node_id)
        if self.anchor is TrustAnchor.UNVERIFIED:
            permissions.require(Permission.INTEGRATION_TRUST_UNVERIFIED, node_id=node_id)


def stamped_trust(declared: Mapping[str, Any], *, actor_id: str, at: datetime) -> StampedTrust:
    """Return ``declared`` with the server's own identity and instant on it.

    Whatever the client sent for "who accepted this" and "when" is discarded
    before validation, not after. An identity a client can choose is what makes
    an audit trail a place people write whatever they like, and a timestamp a
    client can choose is one that can be moved outside the window somebody is
    looking at.

    Raises ``ValueError`` — which the route turns into a refusal naming the
    field — for a declaration the vocabulary itself will not hold: a blank
    reason for accepting an unverified certificate, a private key where the
    certificate goes, a fingerprint that is not one.
    """
    written = {
        name: value
        for name, value in declared.items()
        if name not in {"unverified_accepted_by", "unverified_accepted_at"}
    }
    if str(written.get("unverified_reason") or "").strip():
        written["unverified_accepted_by"] = actor_id
        written["unverified_accepted_at"] = at.isoformat()
    elif "unverified_reason" in written:
        # Present and blank: an attempt to accept an unverified certificate
        # without saying why. Named as the missing thing rather than quietly
        # resolving to the default, which would report success for a decision
        # nobody recorded.
        raise ValueError(
            "accepting an unverified certificate needs a reason. An acceptance that "
            "cannot say why is not a decision anybody took."
        )
    return StampedTrust(section=CertificateTrustSettings.model_validate(written))


def trust_audit_detail(
    integration: str, trust: StampedTrust, *, addresses: Sequence[str]
) -> dict[str, Any]:
    """Return the audit payload for one declaration: scalars, and never a certificate.

    A fixed set of fields, like every other audit payload here, so there is no
    way for a route to add one at the call site — which is how a request body
    ends up in the table. The fingerprints are carried because they are the
    public half's digest and are what an operator compares against the node; the
    certificate is not, because a PEM in an audit trail is bulk that proves
    nothing the fingerprint does not.
    """
    section = trust.section
    payload: dict[str, Any] = {
        "integration": integration,
        "anchor": trust.anchor.value,
        "addresses": [address for address in addresses if address],
    }
    if section.fingerprints:
        payload["fingerprints"] = list(section.fingerprints)
    if section.unverified_reason:
        payload["reason"] = section.unverified_reason
    if section.unverified_accepted_by:
        payload["accepted_by"] = section.unverified_accepted_by
    if section.unverified_accepted_at:
        payload["accepted_at"] = section.unverified_accepted_at
    return payload


async def record_certificate_trust(
    gateway: Any,
    *,
    scope: TenantScope,
    node_id: str,
    integration: str,
    trust: StampedTrust,
    actor_id: str,
) -> tuple[str, ...]:
    """Write what ``integration`` accepts from its endpoint's certificate.

    An upsert on the entry, the whole list written back, exactly as the address
    is — and for the same reason: ``active`` is a sequence, so a patch naming one
    element would replace it with a one-element list and drop every other
    integration the deployment had configured.

    Returns the addresses the declaration ends up covering, so the caller can
    audit what was actually authorised rather than what was asked for.
    """
    config = ConfigService(gateway=gateway, scope=scope)
    effective = await config.resolve(node_id)
    records = _entry_records(effective.config.integrations.active)

    document = trust.document()
    for record in records:
        if record["name"] == integration:
            if document:
                record["trust"] = document
            else:
                record.pop("trust", None)
            break
    else:
        records.append({"name": integration, "enabled": True, "trust": document})

    await config.set_settings(
        node_id,
        {"integrations": {"active": records}},
        actor_id=actor_id,
        actor_kind=ActorKind.USER,
    )
    covered = trust.declaration(
        *(
            str(record.get("base_url", ""))
            for record in records
            if record["name"] == integration and record.get("base_url")
        )
    ).addresses
    logger.info(
        "gateway.integration_trust_recorded",
        integration=integration,
        node_id=node_id,
        # The anchor and the addresses, deliberately. Neither is a secret, and
        # an operator reading a log to find out what this deployment accepts
        # should find the answer rather than a redaction.
        anchor=trust.anchor.value,
        addresses=sorted(covered),
    )
    return covered


async def configured_trust(
    gateway: Any, *, scope: TenantScope, node_id: str
) -> dict[str, CertificateTrust]:
    """Return what each enabled integration accepts, by integration."""
    config = ConfigService(gateway=gateway, scope=scope)
    effective = await config.resolve(node_id)
    return {
        entry.name: entry.certificate_trust()
        for entry in effective.config.integrations.active
        if entry.enabled
    }


async def record_endpoint(
    gateway: Any,
    *,
    scope: TenantScope,
    node_id: str,
    integration: str,
    base_url: str,
    actor_id: str,
) -> None:
    """Point ``integration`` at ``base_url`` in ``node_id``'s own configuration.

    An upsert rather than an append. An operator who corrects a typo is saying
    where the vendor is, not adding a second one, and ``IntegrationsConfig``
    refuses the same vendor twice — so appending would turn the second attempt
    into a validation failure about a document the operator never saw.

    The whole list is written back because ``active`` is a sequence: a patch
    naming one element would replace the sequence with a one-element one and
    silently drop every other integration the team had configured.

    An entry that was switched off is switched back on. Entering an address is
    asking for the vendor to be reached, and leaving it disabled would store the
    value, report success, and change nothing — the shape of failure this whole
    field exists to remove.
    """
    config = ConfigService(gateway=gateway, scope=scope)
    effective = await config.resolve(node_id)
    records = _entry_records(effective.config.integrations.active)

    for record in records:
        if record["name"] == integration:
            record["base_url"] = base_url
            record["enabled"] = True
            break
    else:
        records.append({"name": integration, "base_url": base_url, "enabled": True})

    await config.set_settings(
        node_id,
        {"integrations": {"active": records}},
        actor_id=actor_id,
        actor_kind=ActorKind.USER,
    )
    logger.info(
        "gateway.integration_endpoint_recorded",
        integration=integration,
        node_id=node_id,
        # The address, deliberately. It is not a secret, and an operator reading
        # a log to find out where their deployment thinks the vendor is should
        # find the answer rather than a redaction.
        base_url=base_url,
    )


async def configured_endpoints(gateway: Any, *, scope: TenantScope, node_id: str) -> dict[str, str]:
    """Return the address each enabled integration is pointed at, by integration.

    Empty for a deployment that has pointed nothing anywhere, which is every
    deployment until somebody fills the field in — and is why a client falls
    back to its package's own region rather than refusing to be built.
    """
    config = ConfigService(gateway=gateway, scope=scope)
    effective = await config.resolve(node_id)
    return {
        entry.name: entry.base_url
        for entry in effective.config.integrations.active
        if entry.enabled and entry.base_url
    }


__all__ = [
    "ACTIVE_PATH",
    "Permits",
    "StampedTrust",
    "configured_endpoints",
    "configured_trust",
    "record_certificate_trust",
    "record_endpoint",
    "split_by_destination",
    "stamped_trust",
    "trust_audit_detail",
]

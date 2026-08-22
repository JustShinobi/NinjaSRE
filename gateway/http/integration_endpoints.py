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

from collections.abc import Mapping
from typing import Any

from platform.config_service.service import ConfigService
from platform.credentials.schemas import CredentialSchema
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
        records.append(record)
    return records


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
    "configured_endpoints",
    "record_endpoint",
    "split_by_destination",
]

"""Which integrations a team has, and where their credentials are — not what they are.

The field that is *not* here is the point. There is no ``api_key``, no
``token``, no ``password``, and there never will be: an integration entry
carries a ``credential`` naming a vault entry, and the proxy resolves it at the
network edge. Article IV is satisfied by the absence of a field rather than by a
check that could be relaxed — and because the schema is closed, writing
``api_key`` is refused rather than ignored. Validation then refuses a
secret-shaped value anywhere in the document as a second line.

Everything else an integration needs — the region, the site, the base URL of a
self-hosted instance — is ordinary, non-secret configuration, and it belongs
here because a team's Datadog site is a team's decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import model_validator

from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredStr,
    ConfiguredStrList,
    field_help,
    section_help,
)
from platform.credentials.proxy.trust import CertificateTrust


class CertificateTrustSettings(ConfigSection):
    """What this deployment accepts from the certificate this vendor presents.

    **A public certificate may live here and a private key may not.** The
    certificate is the public half — it is what a browser is shown, it is safe
    in a diagnostic, and it is the anchor a self-signed cluster is verified
    against. The private key is the other half, it authenticates the *server*,
    and nothing on this side of the connection has any use for one. So the
    field refuses a private key by name rather than trusting whoever pastes,
    and the document's own secret scan refuses one wherever else it lands.

    **There is no field here that turns verification off.** The insecure form is
    reached by writing down a reason and who accepted it, both non-empty, and
    the section is closed — so a ``verify: false`` somebody adds is refused
    rather than stored and ignored. Stored and ignored is the worse failure:
    the operator reads the value back, believes it took effect, and the
    behaviour never changes.

    The validation is the proxy's own vocabulary rather than a second copy of
    it. Two validators for one security type is how the two halves end up
    disagreeing about what "verified" means.
    """

    model_config = section_help(
        "What this deployment accepts from this vendor's certificate. Nothing here is "
        "needed for a vendor with a publicly issued certificate."
    )

    fingerprints: Annotated[
        ConfiguredStrList,
        field_help(
            "SHA-256 fingerprints of the certificates you trust at this address, as the "
            "vendor's own interface shows them. One per node: a cluster presents a "
            "different certificate on each. Colons optional."
        ),
    ] = ()
    certificate_pem: Annotated[
        ConfiguredStr | None,
        field_help(
            "The certificate authority this vendor issued itself, pasted whole. Covers "
            "every address whose certificate it signed, which for a cluster is all of "
            "them. Never a private key."
        ),
    ] = None
    unverified_reason: Annotated[
        ConfiguredStr | None,
        field_help(
            "Why this address is reached without verifying its certificate. Required "
            "with the field below and meaningless without it."
        ),
    ] = None
    unverified_accepted_by: Annotated[
        ConfiguredStr | None,
        field_help(
            "Who accepted the unverified certificate. Stamped by the server from the "
            "signed-in principal; a value sent by a client is replaced."
        ),
    ] = None
    unverified_accepted_at: Annotated[
        ConfiguredStr | None,
        field_help("When it was accepted. Stamped by the server."),
    ] = None

    @model_validator(mode="after")
    def _is_a_declaration_the_proxy_can_apply(self) -> CertificateTrustSettings:
        """Refuse anything the trust vocabulary itself would refuse."""
        reason = (self.unverified_reason or "").strip()
        accepted_by = (self.unverified_accepted_by or "").strip()
        if bool(reason) != bool(accepted_by):
            missing = "a reason" if not reason else "who accepted it"
            raise ValueError(
                f"accepting an unverified certificate needs {missing} as well. Both are "
                f"required, because an acceptance that cannot say why or by whom is not "
                f"a decision anybody took."
            )
        self.declaration()
        return self

    def declaration(self, *addresses: str) -> CertificateTrust:
        """Return this section as the declaration the proxy's egress applies."""
        reason = (self.unverified_reason or "").strip()
        accepted_by = (self.unverified_accepted_by or "").strip()
        if reason and accepted_by:
            trust = CertificateTrust.unverified(reason=reason, accepted_by=accepted_by)
        elif self.fingerprints:
            trust = CertificateTrust.pinned(*self.fingerprints)
        elif self.certificate_pem:
            trust = CertificateTrust.with_certificate(self.certificate_pem)
        else:
            trust = CertificateTrust()
        return trust.for_addresses(*addresses) if addresses else trust


class IntegrationSettings(ConfigSection):
    """One integration a team has configured, and where its secret lives."""

    model_config = section_help(
        "One vendor this team is connected to. No secret is entered here — the token "
        "lives in the vault and this entry names it."
    )

    #: Required: an entry that does not say which vendor it configures is not
    #: an entry, and a default would let the omission validate silently.
    name: Annotated[
        ConfiguredStr,
        field_help(
            "Which vendor this entry configures. Required, and must be one of the "
            "integrations this deployment has installed."
        ),
    ]
    credential: Annotated[
        ConfiguredStr,
        field_help("Which stored credential this integration authenticates with."),
    ] = ""
    region: Annotated[
        ConfiguredStr | None,
        field_help("The vendor region to talk to, for vendors that have more than one."),
    ] = None
    site: Annotated[
        ConfiguredStr | None,
        field_help("The vendor site to talk to, for vendors that name one."),
    ] = None
    base_url: Annotated[
        ConfiguredStr | None,
        field_help("The address of your own instance, for a vendor you host yourself."),
    ] = None
    enabled: Annotated[
        bool, field_help("Off keeps the entry and stops anything reaching the vendor.")
    ] = True
    #: Beside the address, because trust is scoped to an address rather than to
    #: a vendor: a declaration authorises what this entry is pointed at and
    #: nothing else, so moving the address is a decision the trust does not
    #: survive.
    trust: Annotated[
        CertificateTrustSettings,
        field_help("What this deployment accepts from this vendor's certificate."),
    ] = CertificateTrustSettings()
    #: The vendor's own non-secret options. Open because the vendor defines
    #: them; scanned for secret shapes like everything else.
    settings: Annotated[
        Mapping[str, Any],
        field_help(
            "Anything else this vendor needs, as it names it. Never a secret: a "
            "secret-shaped value here is refused."
        ),
    ] = {}

    def certificate_trust(self) -> CertificateTrust:
        """Return what this entry accepts, scoped to the address it is pointed at.

        Scoped here rather than by the caller, because the address and the
        declaration are the two halves of one decision and only this object
        holds both. An entry pointed nowhere declares trust for nothing, which
        is what makes moving the address invalidate the declaration made for the
        one before it.
        """
        return self.trust.declaration(*((self.base_url,) if self.base_url else ()))


class IntegrationsConfig(ConfigSection):
    """Every integration a team has configured."""

    model_config = section_help(
        "The vendors this team is connected to. Each entry names a vendor and the stored "
        "credential it uses; no secret is ever typed into configuration."
    )

    active: Annotated[
        tuple[IntegrationSettings, ...],
        field_help("One entry per vendor. A vendor may appear only once."),
    ] = ()

    @model_validator(mode="after")
    def _names_are_distinct(self) -> IntegrationsConfig:
        """Refuse the same vendor configured twice."""
        seen: set[str] = set()
        for integration in self.active:
            if integration.name in seen:
                raise ValueError(f"configures {integration.name!r} more than once")
            seen.add(integration.name)
        return self

    def for_name(self, name: str) -> IntegrationSettings | None:
        """Return the entry for ``name``, or ``None``."""
        for integration in self.active:
            if integration.name == name:
                return integration
        return None

    def enabled_names(self) -> tuple[str, ...]:
        """Return the integrations a run may actually reach, in declared order."""
        return tuple(entry.name for entry in self.active if entry.enabled)

    def referenced_names(self) -> tuple[str, ...]:
        """Return every integration this configuration names, deduplicated."""
        return tuple(dict.fromkeys(entry.name for entry in self.active if entry.name))

    def credential_references(self) -> tuple[str, ...]:
        """Return the vault entries this configuration points at."""
        return tuple(dict.fromkeys(entry.credential for entry in self.active if entry.credential))


INTEGRATIONS_FIELDS: tuple[str, ...] = tuple(IntegrationsConfig.model_fields)
INTEGRATION_FIELDS: tuple[str, ...] = tuple(IntegrationSettings.model_fields)


__all__ = [
    "INTEGRATIONS_FIELDS",
    "INTEGRATION_FIELDS",
    "IntegrationSettings",
    "IntegrationsConfig",
]

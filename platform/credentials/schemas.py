"""What a given vendor's credential is made of, declared once per integration.

A credential is rarely one string. Datadog wants an API key and an application
key, AWS wants an access key, a secret, and sometimes a session token, and a
self-hosted Grafana wants a token or a username and password but not both. FR-004
says each vendor declares that shape, and FR-005 says the vault checks a write
against it before anything is persisted.

Validating on write is the whole value. A key stored with a trailing newline —
the classic result of a copy-paste from a terminal — is indistinguishable from a
correct one until the first call, and the first call happens during an incident.
Rejecting it at the moment an operator is looking at the screen costs them ten
seconds; finding out later costs an investigation.

Two rules hold everywhere in this module.

**A validation message never quotes a value.** It names the field and says what
was wrong with its shape. ``"api_key must not contain whitespace"`` is
actionable; ``"api_key was 'a3f1…\\n'"`` is a leak.

**A field says whether it is secret.** Not everything in a credential is one — a
region, a site, an account id are configuration a capability may legitimately
see — and ``FieldKind.PUBLIC`` is how an integration says so. The distinction is
what lets the health check report "configured for eu1" without reporting a key.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

from platform.credentials.errors import CredentialSchemaViolation, UnknownIntegration

#: The longest a single credential field may be. Generous enough for a PEM
#: private key, bounded so a paste of the wrong file cannot become a row that
#: breaks every query that touches the table.
MAX_CREDENTIAL_FIELD_CHARS: Final[int] = 16_384

#: Words a field name carries that read as an acronym once capitalised, rather
#: than as a word once titled. ``_derive_label`` consults this so a fallback
#: label reads "API Key" and "Access Key ID" rather than "Api key" and "Access
#: key id" — the same mangling `.capitalize()` on the raw name already produced
#: before this module declared a label of its own.
_LABEL_ACRONYMS: Final[frozenset[str]] = frozenset(
    {
        "aws",
        "gcp",
        "api",
        "id",
        "url",
        "uri",
        "sso",
        "sql",
        "json",
        "ssh",
        "jwt",
        "pem",
        "sas",
        "arn",
        "iam",
        "sid",
    }
)


def _derive_label(name: str) -> str:
    """Return a human label derived from a declared field ``name``.

    The fallback for a field whose vendor package has not (yet) declared a
    ``label`` of its own — never the source of truth, and never claimed to be
    one: a derived label is a best-effort reading of the field's own name, not
    a fact anybody wrote down.
    """
    words = [word for word in name.split("_") if word]
    return " ".join(
        word.upper() if word.lower() in _LABEL_ACRONYMS else word.capitalize() for word in words
    )


#: The schemes an endpoint field accepts. A vendor is reached over HTTP by
#: everything in this catalogue, and a field that took any scheme would let an
#: address the proxy cannot forward through validation and fail it later.
_ENDPOINT_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})


class FieldKind(StrEnum):
    """Whether a field is the secret, the address, or the configuration around them.

    ``ENDPOINT`` is separated from ``PUBLIC`` because the two are stored in
    different places and that is a property of what they are rather than a
    routing decision somebody made. Public configuration is part of the
    credential and lives in the vault beside it. An address is not part of a
    credential at all — it is where the deployment points, the proxy already
    reads its egress allow-list from the configuration tree, and putting it in
    the vault would make the one fact the client needs the one fact nothing
    outside the proxy may read.
    """

    SECRET = "secret"
    PUBLIC = "public"
    ENDPOINT = "endpoint"


@dataclass(frozen=True, slots=True)
class CredentialField:
    """One named part of a credential, and what a valid one looks like.

    ``pattern`` is a full-match regular expression. It is worth setting when the
    vendor's format is genuinely fixed — a 32-character hex Datadog key, an
    ``AKIA``-prefixed AWS access key id — and worth leaving unset otherwise: a
    pattern that is nearly right rejects the deployment that is using the
    vendor's newer key format, and the operator has no way to override it.

    ``label``, ``min_scope`` and ``guide_url`` are what a credential form needs
    beyond validation: what a person calls this field, the least the vendor's
    own permission model has to grant it, and where to read the vendor's own
    setup steps. All three default to blank, and a blank one is never invented
    downstream — ``min_scope`` and ``guide_url`` stay blank until a contributor
    who knows the vendor's real minimum writes it here; ``label`` alone has a
    derived fallback, through ``display_label``, because a field's own name is
    always enough to guess *some* human words for it.
    """

    name: str
    description: str = ""
    required: bool = True
    kind: FieldKind = FieldKind.SECRET
    min_length: int = 1
    pattern: str | None = None
    #: Fields that may appear in place of this one. A Grafana credential is a
    #: token *or* a username and password, and neither is unconditionally
    #: required.
    alternatives: tuple[str, ...] = ()
    #: What a person calls this field — "API key", never "api_key". Declared
    #: beside the vendor that needs it; read this through ``display_label``,
    #: which is what falls back when a vendor package has not declared one.
    label: str = ""
    #: The least the vendor's own permission model has to grant this field —
    #: "read-only", "BigQuery Data Viewer", a scope name. Blank when the real
    #: minimum is not confidently known: a guessed scope is a permission an
    #: operator pastes into the vendor's own console and finds insufficient, or
    #: excessive, during an incident rather than before one.
    min_scope: str = ""
    #: A step-by-step guide for obtaining this field's value, when the
    #: deployment has one to offer. Blank is the ordinary case.
    guide_url: str = ""

    @property
    def is_secret(self) -> bool:
        """Return whether this field holds material the agent must never see."""
        return self.kind is FieldKind.SECRET

    @property
    def is_endpoint(self) -> bool:
        """Return whether this field is the address the vendor is reached at."""
        return self.kind is FieldKind.ENDPOINT

    @property
    def display_label(self) -> str:
        """Return ``label``, or a label derived from ``name`` when none is declared."""
        declared = self.label.strip()
        return declared if declared else _derive_label(self.name)

    def problems(self, value: str | None) -> tuple[str, ...]:
        """Return what is wrong with ``value``, naming the field and never quoting it."""
        if value is None or value == "":
            return () if not self.required else (f"{self.name} is required and was not supplied",)
        found: list[str] = []
        if len(value) < self.min_length:
            found.append(f"{self.name} is shorter than the {self.min_length} characters required")
        if len(value) > MAX_CREDENTIAL_FIELD_CHARS:
            found.append(
                f"{self.name} is longer than the {MAX_CREDENTIAL_FIELD_CHARS} characters permitted"
            )
        if value != value.strip():
            found.append(
                f"{self.name} has leading or trailing whitespace, which is almost always "
                f"a copy-paste artefact rather than part of the credential"
            )
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            found.append(f"{self.name} does not match the format this vendor issues")
        if self.is_endpoint:
            found.extend(self._address_problems(value))
        return tuple(found)

    def _address_problems(self, value: str) -> tuple[str, ...]:
        """Return what is wrong with ``value`` as an address, never quoting it.

        An operator's first attempt is almost always ``host:port`` with no
        scheme, which ``urlsplit`` reads as a scheme of ``host`` and a path of
        the port — plausible, wrong, and silent. Saying which half is missing is
        the difference between a fix and a second attempt at the same guess.
        """
        split = urlsplit(value.strip())
        if split.scheme.lower() not in _ENDPOINT_SCHEMES:
            return (
                f"{self.name} must start with http:// or https:// — an address without "
                f"a scheme is not one this deployment can tell how to reach",
            )
        if not split.hostname:
            return (f"{self.name} names no host, so there is nowhere for a call to go",)
        if split.query or split.fragment:
            return (
                f"{self.name} is a base address rather than a request: a query or "
                f"fragment here would be sent on every call this integration makes",
            )
        return ()


@dataclass(frozen=True, slots=True)
class CredentialSchema:
    """Every field one integration's credential may carry.

    Declared beside the integration it describes, so adding a vendor is one
    package and no edit anywhere else — the property that has to hold if a
    catalogue is going to be addable one at a time.
    """

    integration: str
    fields: tuple[CredentialField, ...]

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError(f"the credential schema for {self.integration!r} declares no fields")
        names = [declared.name for declared in self.fields]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(
                f"the credential schema for {self.integration!r} declares "
                f"{sorted(duplicates)} more than once"
            )
        endpoints = [declared.name for declared in self.fields if declared.is_endpoint]
        if len(endpoints) > 1:
            raise ValueError(
                f"the credential schema for {self.integration!r} declares more than one "
                f"endpoint ({', '.join(sorted(endpoints))}), and a client asked to address "
                f"two places would have to pick one"
            )

    def get(self, name: str) -> CredentialField | None:
        """Return the field called ``name``, or ``None``."""
        return next((declared for declared in self.fields if declared.name == name), None)

    @property
    def field_names(self) -> tuple[str, ...]:
        """Return every declared field name, in declaration order."""
        return tuple(declared.name for declared in self.fields)

    @property
    def required_names(self) -> tuple[str, ...]:
        """Return the names of the fields that must be supplied."""
        return tuple(declared.name for declared in self.fields if declared.required)

    @property
    def secret_names(self) -> tuple[str, ...]:
        """Return the names of the fields the agent must never see."""
        return tuple(declared.name for declared in self.fields if declared.is_secret)

    @property
    def endpoint_names(self) -> tuple[str, ...]:
        """Return the address fields, which are stored as configuration rather than in the vault.

        A tuple rather than an optional single name so that a caller splitting a
        submitted form by destination writes one comprehension instead of a
        branch, and so the empty case — every vendor with a real public API —
        needs no special reading.
        """
        return tuple(declared.name for declared in self.fields if declared.is_endpoint)

    @property
    def vault_names(self) -> tuple[str, ...]:
        """Return the fields that belong in the vault: everything but the address."""
        return tuple(declared.name for declared in self.fields if not declared.is_endpoint)

    def for_vault(self) -> CredentialSchema | None:
        """Return this schema without its address fields, or ``None`` if nothing is left.

        The vault validates what it is asked to store, and an address is not
        stored there — so validating the vault's half against the whole schema
        refuses a perfectly good write for the absence of a field that went
        somewhere else. ``None`` is the honest answer for a vendor that declares
        an address and no credential at all: there is nothing for the vault to
        hold, and a schema with no fields is one this class refuses to build.
        """
        kept = tuple(declared for declared in self.fields if not declared.is_endpoint)
        if not kept:
            return None
        return CredentialSchema(integration=self.integration, fields=kept)

    def validate(self, values: Mapping[str, str]) -> None:
        """Raise ``CredentialSchemaViolation`` unless ``values`` fits this schema.

        Reports every problem at once. An operator entering a credential wants
        to fix all of it in one pass, not to discover the second mistake after
        correcting the first.
        """
        problems: list[str] = []
        for declared in self.fields:
            supplied = values.get(declared.name)
            if supplied is None and declared.alternatives:
                if any(values.get(other) for other in declared.alternatives):
                    continue
                problems.append(
                    f"one of {declared.name} or {', '.join(declared.alternatives)} is required "
                    f"and none was supplied"
                )
                continue
            problems.extend(declared.problems(supplied))

        unknown = sorted(set(values) - set(self.field_names))
        if unknown:
            problems.append(
                f"{', '.join(unknown)} is not part of this integration's credential. "
                f"Declared fields: {', '.join(self.field_names)}"
            )
        if problems:
            raise CredentialSchemaViolation(integration=self.integration, problems=problems)


@dataclass(slots=True)
class CredentialSchemaRegistry:
    """Which schema applies to which integration.

    A registry rather than a lookup on the integration package, because
    ``platform/`` sits below ``integrations/`` in the tier table and may not
    import it. Composition fills this in; the vault and the proxy read it.
    """

    _schemas: dict[str, CredentialSchema] = field(default_factory=dict)

    @classmethod
    def from_schemas(cls, *schemas: CredentialSchema) -> CredentialSchemaRegistry:
        """Return a registry holding ``schemas``."""
        registry = cls()
        for schema in schemas:
            registry.register(schema)
        return registry

    def register(self, schema: CredentialSchema) -> None:
        """Add ``schema``, replacing any schema already held for its integration."""
        self._schemas[schema.integration] = schema

    def register_all(self, schemas: Iterable[CredentialSchema]) -> None:
        """Add every schema in ``schemas``."""
        for schema in schemas:
            self.register(schema)

    def get(self, integration: str) -> CredentialSchema:
        """Return the schema for ``integration``, or raise ``UnknownIntegration``."""
        schema = self._schemas.get(integration)
        if schema is None:
            raise UnknownIntegration(integration, known=self.integrations())
        return schema

    def has(self, integration: str) -> bool:
        """Return whether a schema is declared for ``integration``."""
        return integration in self._schemas

    def integrations(self) -> tuple[str, ...]:
        """Return every integration with a declared schema, in name order."""
        return tuple(sorted(self._schemas))


__all__ = [
    "MAX_CREDENTIAL_FIELD_CHARS",
    "CredentialField",
    "CredentialSchema",
    "CredentialSchemaRegistry",
    "FieldKind",
]

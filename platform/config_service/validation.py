"""Three passes before anything is stored, and one of them is about credentials.

**Shape.** The document is built into the declared schema, and every field that
could not be read becomes a field-level error at the path the operator wrote it
at. Undeclared keys are errors too — a typo in a field name is otherwise a
setting that is stored, shown in the console, and never read, and nothing in the
system can tell that apart from a field that works.

**Cross-reference.** A capability or integration name that nothing answers to is
an error at the write rather than a surprise at three in the morning (SC-004).
The catalogue is a port because this is tier 3; the composition root supplies a
reader over the live registry.

**Secrets.** Every string value is scanned by the same guardrail engine that
scans evidence, and a match is refused with a pointer to the vault (FR-013). The
scan is per field rather than over the serialised document, so the refusal can
name the path — and it never quotes the value, because a refusal that echoed the
secret would put it in the log the refusal was keeping it out of.

The passes run in that order and all of them run: an operator fixing a
configuration one problem per submission stops using configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from platform.config_service import paths
from platform.config_service.catalogue import (
    CapabilityCatalogueReader,
    IntegrationDirectory,
)
from platform.config_service.errors import (
    ConfigInvalid,
    FieldError,
    SecretInConfiguration,
)
from platform.config_service.field_policy import (
    PolicySet,
    constraint_errors,
    missing_required,
)
from platform.config_service.schema.root import RootConfig
from platform.guardrails.engine import GuardrailEngine

#: What a value is scanned as. The field's own name is included so the labelled
#: rules — ``aws_secret_access_key = …``, ``authorization: …`` — fire the way
#: they would on the line an operator pasted it from. That matters most in the
#: two free-form regions, where the key an operator invents is the only evidence
#: of what the value is. Structural shapes such as a PEM block or an access-key
#: id match on the value alone and do not need it.
_SCAN_TEMPLATE = "{label} = {value}"

#: Fields whose values are *references* by construction. Scanning one with its
#: own name attached produces ``credential = datadog-prod``, which the generic
#: labelled-secret rule reads as a secret behind a label — and the label is the
#: field that exists precisely so the secret is somewhere else. The value alone
#: is still scanned, so a credential genuinely pasted here is still refused by
#: the structural rules that do not need a label.
REFERENCE_FIELD_NAMES: frozenset[str] = frozenset({"credential"})


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """What validation made of a document, and everything wrong with it."""

    config: RootConfig = field(default_factory=RootConfig)
    errors: tuple[FieldError, ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether the document may be stored."""
        return not self.errors

    def raise_if_invalid(self) -> RootConfig:
        """Return the configuration, or raise carrying every field-level error."""
        if self.errors:
            raise ConfigInvalid(self.errors)
        return self.config

    def paths(self) -> tuple[str, ...]:
        """Return the paths that failed, in the order they were reported."""
        return tuple(error.path for error in self.errors)


@dataclass(frozen=True, slots=True)
class ConfigValidator:
    """The three passes, over whichever catalogue and ruleset are live.

    ``catalogue`` and ``integrations`` are optional so this class is usable
    before a composition root exists — a merge test does not need a registry.
    The composition root always supplies both, and ``ConfigService`` will not
    start without them, because a deployment that skipped cross-reference
    validation would discover its dangling references during an incident.
    """

    catalogue: CapabilityCatalogueReader | None = None
    integrations: IntegrationDirectory | None = None
    guardrails: GuardrailEngine = field(default_factory=GuardrailEngine)

    def validate(
        self, values: Mapping[str, Any], policies: PolicySet | None = None
    ) -> ValidationOutcome:
        """Return what ``values`` builds to, and everything wrong with it.

        ``policies`` is the accumulated field policy in force at the node, and
        supplying it adds the required-field and constraint passes. Without it,
        only shape, cross-reference, and secrets are checked — which is the
        right set for a node's own partial document, where a field required at
        the leaf may legitimately be supplied by an ancestor.
        """
        config, errors = RootConfig.read(values)
        found = list(errors)
        found.extend(self.cross_reference_errors(config))
        found.extend(self.secret_errors(values))
        if policies is not None:
            found.extend(
                FieldError(path=path, message="is required and has no value in this chain")
                for path in missing_required(values, policies)
            )
            found.extend(constraint_errors(values, policies))
        return ValidationOutcome(config=config, errors=tuple(found))

    def cross_reference_errors(self, config: RootConfig) -> tuple[FieldError, ...]:
        """Return the references in ``config`` that nothing installed answers to."""
        found: list[FieldError] = []
        if self.catalogue is not None:
            installed = set(self.catalogue.names())
            found.extend(
                FieldError(
                    path=f"capabilities.{name}",
                    message="names a capability this deployment has not installed",
                )
                for name in config.capability_references()
                if name not in installed
            )
        if self.integrations is not None:
            available = set(self.integrations.names())
            found.extend(
                FieldError(
                    path=f"integrations.{name}",
                    message="names an integration this deployment has not installed",
                )
                for name in config.integration_references()
                if name not in available
            )
        return tuple(found)

    def secret_errors(self, values: Mapping[str, Any]) -> tuple[FieldError, ...]:
        """Return one error per field whose value looks like a credential."""
        return tuple(
            FieldError(
                path=path,
                message=(
                    f"matches the {rule!r} secret shape. Configuration holds references, "
                    f"never secrets: store the credential in the vault and put its "
                    f"reference here."
                ),
            )
            for path, rule in self.secret_shaped(values)
        )

    def secret_shaped(self, values: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
        """Return the ``(path, rule)`` pairs whose values look like credentials.

        Walks into lists as well as sections. A credential pasted into the third
        integration entry is a credential, and a scan that only looked at the
        list as a whole would miss every one of them.
        """
        found: list[tuple[str, str]] = []
        for path, value in paths.scalars(values):
            if not isinstance(value, str) or not value:
                continue
            result = self.guardrails.scan(_scan_text(path, value))
            if not result.clean:
                found.append((path, result.rules_fired[0]))
        return tuple(found)

    def check_secrets(self, values: Mapping[str, Any]) -> None:
        """Raise ``SecretInConfiguration`` on the first secret-shaped value.

        The single-error form, for a write path that has already passed shape
        validation and wants the refusal to be about the credential rather than
        one line in a list.
        """
        for path, rule in self.secret_shaped(values):
            raise SecretInConfiguration(path=path, rule=rule)


def _scan_text(path: str, value: str) -> str:
    """Return what the guardrail engine is given for the value at ``path``."""
    label = paths.split(path)[-1]
    if label in REFERENCE_FIELD_NAMES:
        return value
    return _SCAN_TEMPLATE.format(label=label, value=value)


__all__ = ["REFERENCE_FIELD_NAMES", "ConfigValidator", "ValidationOutcome"]

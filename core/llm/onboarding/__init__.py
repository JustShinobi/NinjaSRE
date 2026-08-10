"""Onboarding one model provider, nine times, with nothing special about any of them.

Each module here declares one ``ProviderOnboarding``: what the provider is
called, which fields it needs, what a sensible default model is, and the one or
two sentences somebody setting it up for the first time needs. That is all a
provider gets to say, which is the point — Article VI is only true if the local
provider is set up through the same nine-branch-free path as the hosted ones,
and a surface with a special case for one of them is a surface where it is not.

The directory is walked rather than listed, so a tenth provider is a module
here and a row in the constants — the same shape adding an adapter has.

**This lives beside the adapters it describes rather than inside a surface.**
Two surfaces read it now: the CLI's guided first run, and the API's
``/v1/providers`` family, which the console renders. Those are two tier-1
packages and they may not import each other, so a copy in either would have
become a second answer to "what can this deployment be pointed at" — and the
second answer is the one that ages.

Nothing here is a credential. A descriptor says what to *ask for*; the value an
operator enters goes to the vault through the same route any integration's does,
and no type in this package has a field one could sit in.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from config.constants.llm import LOCAL_PROVIDERS, SUPPORTED_PROVIDERS
from platform.credentials.fields import CredentialFieldSpec
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind


class UnknownProviderError(LookupError):
    """A provider this build declares no onboarding for.

    Raised rather than defaulted, for the reason ``UnknownModelError`` is: a
    first run that quietly configured a different provider from the one somebody
    chose is one whose result nobody can explain.
    """

    def __init__(self, provider_id: str, known: Sequence[str]) -> None:
        super().__init__(
            f"{provider_id!r} is not a provider this build knows how to set up. "
            f"Choose one of: {', '.join(known)}"
        )
        self.provider_id = provider_id
        self.known = tuple(known)


@dataclass(frozen=True, slots=True)
class ProviderOnboarding:
    """What a surface needs to set one provider up."""

    provider_id: str
    display_name: str
    default_model: str
    fields: tuple[CredentialFieldSpec, ...] = ()
    guidance: str = ""
    #: Where an operator gets the credential. Shown before the prompt, because
    #: "paste your API key" is not an instruction to somebody who has never been
    #: to that console.
    where_to_get_it: str = ""
    models: tuple[str, ...] = ()
    extras: tuple[str, ...] = field(default_factory=tuple)

    @property
    def local(self) -> bool:
        """Return whether this provider runs on the operator's own infrastructure."""
        return self.provider_id in LOCAL_PROVIDERS

    @property
    def install_hint(self) -> str:
        """Return how to install this provider's optional extra, if it has one."""
        if not self.extras:
            return ""
        return f"pip install 'ninjasre[{self.extras[0]}]'"

    def to_record(self) -> dict[str, object]:
        """Return this descriptor as a JSON-serialisable document.

        Field *names*, labels and help text; never a value, because there is no
        value here to return. This is what makes the descriptor servable from a
        route without the route becoming a credential-reading path.
        """
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "default_model": self.default_model,
            "fields": [declared.to_record() for declared in self.fields],
            "guidance": self.guidance,
            "where_to_get_it": self.where_to_get_it,
            "models": list(self.models),
            "local": self.local,
            "install_hint": self.install_hint,
        }


_REGISTRY: dict[str, ProviderOnboarding] = {}


def _discover() -> Mapping[str, ProviderOnboarding]:
    """Return every provider onboarding declared in this package.

    Walked rather than listed. A registry somebody has to remember to add to is
    a registry that is missing the provider added last Thursday.
    """
    if _REGISTRY:
        return _REGISTRY

    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        imported = importlib.import_module(f"{__name__}.{module.name}")
        declared = getattr(imported, "ONBOARDING", None)
        if isinstance(declared, ProviderOnboarding):
            _REGISTRY[declared.provider_id] = declared
    return _REGISTRY


def onboarding_for(provider_id: str) -> ProviderOnboarding:
    """Return how to onboard ``provider_id``.

    Raises:
        UnknownProviderError: nothing here knows how to set that provider up.
    """
    found = _discover().get(provider_id)
    if found is None:
        raise UnknownProviderError(provider_id, sorted(_discover()))
    return found


def all_onboardings() -> tuple[ProviderOnboarding, ...]:
    """Return every provider's onboarding, in the constants' declared order.

    The declared order rather than alphabetical, so the list an operator is
    shown is the one the platform documents rather than one that happens to put
    a vendor first because of its initial.
    """
    known = _discover()
    return tuple(known[name] for name in SUPPORTED_PROVIDERS if name in known)


def provider_names() -> Sequence[str]:
    """Return the identifiers a surface offers, in declared order."""
    return [onboarding.provider_id for onboarding in all_onboardings()]


def credential_schema_for(provider_id: str) -> CredentialSchema:
    """Return the vault schema a provider's credential is validated against.

    A provider is not an installed integration — it ships no vendor package —
    but its key is stored the same way, under the same handle shape, through the
    same route. This is the translation that makes that one path rather than
    two, and it lives beside the descriptor so a tenth provider still needs
    nothing but a module and a constant.

    No pattern is imposed. A provider's key format is the provider's business
    and changes without notice; a nearly-right pattern would refuse the
    deployment that is already using the newer format, with no way to override.

    Raises:
        UnknownProviderError: nothing here knows how to set that provider up.
    """
    onboarding = onboarding_for(provider_id)
    return CredentialSchema(
        integration=provider_id,
        fields=tuple(
            CredentialField(
                name=declared.name,
                description=declared.help,
                required=declared.required,
                kind=FieldKind.SECRET if declared.secret else FieldKind.PUBLIC,
            )
            for declared in onboarding.fields
        ),
    )


#: Every supported provider must have one of these. The contract suite asserts
#: it, because a provider that is adaptable but not onboardable is one nobody
#: reaches — which is provider neutrality failing at the surface instead of in
#: the adapter layer.
EXPECTED_PROVIDERS: Final[tuple[str, ...]] = SUPPORTED_PROVIDERS


__all__ = [
    "EXPECTED_PROVIDERS",
    "ProviderOnboarding",
    "UnknownProviderError",
    "all_onboardings",
    "credential_schema_for",
    "onboarding_for",
    "provider_names",
]

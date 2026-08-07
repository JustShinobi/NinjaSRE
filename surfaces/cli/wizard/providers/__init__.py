"""Onboarding one model provider, nine times, with nothing special about any of them.

Each module here declares one ``ProviderOnboarding``: what the provider is
called, which fields it needs, what a sensible default model is, and the one or
two sentences somebody setting it up for the first time needs. That is all a
provider gets to say, which is the point — Article VI is only true if the local
provider is set up through the same nine-branch-free path as the hosted ones,
and a wizard with a special case for one of them is a wizard where it is not.

The directory is walked rather than listed, so a tenth provider is a module
here and a row in the constants — the same shape adding an adapter has.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from config.constants.llm import LOCAL_PROVIDERS, SUPPORTED_PROVIDERS
from surfaces.cli.errors import ConfigurationError
from surfaces.cli.models import CredentialFieldSpec


@dataclass(frozen=True, slots=True)
class ProviderOnboarding:
    """What the wizard needs to set one provider up."""

    provider_id: str
    display_name: str
    default_model: str
    fields: tuple[CredentialFieldSpec, ...] = ()
    guidance: str = ""
    #: Where an operator gets the credential. Printed before the prompt, because
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
        ConfigurationError: nothing here knows how to set that provider up.
    """
    found = _discover().get(provider_id)
    if found is None:
        raise ConfigurationError(
            f"{provider_id!r} is not a provider this build knows how to set up",
            remedy=f"choose one of: {', '.join(sorted(_discover()))}",
        )
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
    """Return the identifiers the wizard offers, in declared order."""
    return [onboarding.provider_id for onboarding in all_onboardings()]


#: Every supported provider must have one of these. The contract suite asserts
#: it, because a provider that is adaptable but not onboardable is one nobody
#: reaches — which is provider neutrality failing at the surface instead of in
#: the adapter layer.
EXPECTED_PROVIDERS: Final[tuple[str, ...]] = SUPPORTED_PROVIDERS


__all__ = [
    "EXPECTED_PROVIDERS",
    "ProviderOnboarding",
    "all_onboardings",
    "onboarding_for",
    "provider_names",
]

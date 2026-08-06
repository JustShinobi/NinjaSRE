"""Every installed integration, found by walking the package rather than listing it.

The catalogue is three vendors today and roughly eighty-five by the end of
wave 6. A module that listed them would be a module somebody has to remember to
edit, and the thing they would forget is exactly the thing SC-002 is about — an
integration with no proxy path is an integration with an in-process credential.

So discovery walks ``integrations/`` and collects the ``DESCRIPTOR`` each
package exposes. Adding a vendor is one package and no edit anywhere else;
forgetting the descriptor is a failure in the catalogue-wide contract suite the
day it lands.

**Import failures are not swallowed.** A package that raises on import is a
broken integration, and a registry that quietly skipped it would report a
catalogue that is missing a vendor as a catalogue that is complete — which is
the failure discovered at 03:00 when the one integration that mattered turns out
never to have loaded.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Final

import integrations
from platform.credentials.descriptor import IntegrationDescriptor
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.schemas import CredentialSchemaRegistry

#: What a vendor package exposes to be discovered.
DESCRIPTOR_ATTRIBUTE: Final = "DESCRIPTOR"

#: Packages under ``integrations/`` that are not vendors. ``_base`` is the
#: shared client every vendor sits on; the leading underscore says so, and this
#: is where the convention becomes enforcement.
NON_VENDOR_PACKAGES: Final[frozenset[str]] = frozenset({"_base"})


def discover() -> dict[str, IntegrationDescriptor]:
    """Return every installed integration's descriptor, keyed by name.

    Walks the package tree on each call rather than caching. Discovery is a
    handful of imports Python has already done, and a cache here would be a
    cache that has to be invalidated when a deployment installs a vendor at
    runtime — which is a feature this does not need and a bug it would have.
    """
    found: dict[str, IntegrationDescriptor] = {}
    for module in pkgutil.iter_modules(integrations.__path__):
        if not module.ispkg or module.name in NON_VENDOR_PACKAGES:
            continue
        package = importlib.import_module(f"{integrations.__name__}.{module.name}")
        descriptor = getattr(package, DESCRIPTOR_ATTRIBUTE, None)
        if descriptor is None:
            raise LookupError(
                f"the integration package {module.name!r} exposes no "
                f"{DESCRIPTOR_ATTRIBUTE}, so nothing knows what its credential looks "
                f"like, which hosts it may reach, or how its secret enters a request"
            )
        if not isinstance(descriptor, IntegrationDescriptor):
            raise TypeError(
                f"{module.name}.{DESCRIPTOR_ATTRIBUTE} is a "
                f"{type(descriptor).__name__}, not an IntegrationDescriptor"
            )
        found[descriptor.name] = descriptor
    return found


def descriptors() -> dict[str, IntegrationDescriptor]:
    """Return every installed integration's descriptor, keyed by name."""
    return discover()


def integration_names() -> tuple[str, ...]:
    """Return the installed integrations, in name order."""
    return tuple(sorted(discover()))


def credential_schemas() -> CredentialSchemaRegistry:
    """Return a schema registry holding every installed integration's schema.

    This is what composition hands the vault, and it is why ``platform/`` never
    imports ``integrations/``: the tier below is given the declarations rather
    than going to look for them.
    """
    registry = CredentialSchemaRegistry()
    registry.register_all(descriptor.schema for descriptor in discover().values())
    return registry


def injection_rules() -> InjectionRuleRegistry:
    """Return a rule registry holding every installed integration's injection rule."""
    registry = InjectionRuleRegistry()
    registry.register_all(descriptor.rule for descriptor in discover().values())
    return registry


__all__ = [
    "DESCRIPTOR_ATTRIBUTE",
    "NON_VENDOR_PACKAGES",
    "credential_schemas",
    "descriptors",
    "discover",
    "injection_rules",
    "integration_names",
]

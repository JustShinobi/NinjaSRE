"""Backend registration: adding an integration adds a module, not an edit.

Discovery walks this package and takes what it finds, for the same reason the
capability registry does. A central list here would be a merge conflict on
every integration, and a backend that exists but was never registered would be
silently replaced by the generic one — which answers ``{}`` to everything, so
the scenario would still run and would simply stop finding anything. That is
the worst failure shape available: green, quiet, and wrong.

A backend module declares ``BACKENDS``, a tuple of ``MockBackend``. Nothing
else. An integration with no module is not broken — it gets the generic JSON
vendor, which is the right answer for the many vendors whose clients read a
document and treat an empty one as "nothing to report". A module is worth
writing when a vendor's empty answer has a *shape*: a Kubernetes list, a
Prometheus result envelope, an AWS query-protocol XML document.
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import cache

from tests.harness.backends.base import (
    GENERIC_BACKEND,
    MockBackend,
    MockVendorBoundary,
    VendorCall,
    host_map,
    json_response,
    text_response,
    xml_response,
)

#: Modules in this package that declare no backend and are never walked for one.
_SUPPORT_MODULES = frozenset({"base", "recording"})


@cache
def registry() -> dict[str, MockBackend]:
    """Return every declared backend, keyed by integration name.

    Raises:
        ImportError: a module in this package could not be imported. A backend
            missing because its module raised would be indistinguishable from
            one nobody wrote, and the run would quietly answer ``{}``.
    """
    found: dict[str, MockBackend] = {}
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name in _SUPPORT_MODULES or module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        for backend in getattr(module, "BACKENDS", ()):
            found[backend.integration] = backend
    return found


def backend_for(integration: str) -> MockBackend:
    """Return the backend for ``integration``, or the generic JSON vendor."""
    return registry().get(integration, GENERIC_BACKEND)


__all__ = [
    "GENERIC_BACKEND",
    "MockBackend",
    "MockVendorBoundary",
    "VendorCall",
    "backend_for",
    "host_map",
    "json_response",
    "registry",
    "text_response",
    "xml_response",
]

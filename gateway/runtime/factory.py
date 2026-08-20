"""The no-argument factory a deployment's investigation runtime setting names.

Composing a runtime means choosing a provider and a capability catalogue
(``gateway/http/asgi.py``'s own words for it, in the module docstring naming
this factory's shape). Both are resolved from the process environment here,
the same way every other first-class collaborator in this tier already is:
the provider through ``core.llm.factory``, the one call the rest of the
product makes for a model client, and the capability catalogue through the
validated registry every capability package declares itself into by being
imported. Neither call takes an argument, which is what lets this factory be
named — not written — by an operator's configuration.

The credential proxy is deliberately not composed here.
``gateway/http/lifespan.py`` binds it once for the whole process, before any
request is served, and every vendor tool already reads that one binding;
composing a second one in this factory would be a duplicate seam, not a
stronger one.
"""

from __future__ import annotations

from capabilities.registry import build_registry
from core.llm.factory import get_llm
from gateway.http.services import InvestigationRunner
from gateway.runtime.investigator import ReActInvestigationRunner


def build_investigator() -> InvestigationRunner:
    """Return the first-party investigator: the canonical loop, fully composed.

    Takes no argument, in the shape a factory reference requires. The
    registry is built once per process — ``build_registry`` already caches it
    — so naming this factory costs one package walk, not one per
    investigation.
    """
    return ReActInvestigationRunner(llm=get_llm(), registry=build_registry())


__all__ = ["build_investigator"]

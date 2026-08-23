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
from config.constants.config_service import MODEL_ROLE_INVESTIGATOR
from core.llm.factory import get_llm
from gateway.http.services import InvestigationRunner
from gateway.runtime.investigator import ReActInvestigationRunner

#: The role the operator's model choice is stored and published under.
#:
#: Spelled here rather than passed as a literal because the whole defect was one
#: word: ``gateway/http/serve.py`` reads the configuration tree at boot and
#: publishes the binding under this name, and this factory asked for the default
#: role, which nothing binds. Every investigation therefore ran on whatever the
#: deployment manifest named, and an operator who chose a provider in the
#: console had no way to see that their choice was being read under a name
#: nobody wrote to.
INVESTIGATOR_ROLE = MODEL_ROLE_INVESTIGATOR


def build_investigator() -> InvestigationRunner:
    """Return the first-party investigator: the canonical loop, fully composed.

    Takes no argument, in the shape a factory reference requires. The
    registry is built once per process — ``build_registry`` already caches it
    — so naming this factory costs one package walk, not one per
    investigation.
    """
    return ReActInvestigationRunner(llm=get_llm(INVESTIGATOR_ROLE), registry=build_registry())


__all__ = ["INVESTIGATOR_ROLE", "build_investigator"]

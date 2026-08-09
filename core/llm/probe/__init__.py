"""What one model can actually do, measured rather than read off a model card.

``preflight`` describes a provider and ``verification`` decides whether the
configured model meets the contract. This package answers a third question the
other two cannot: *of the models this endpoint serves, which ones would work*,
and what are the real numbers for the one chosen.

Three things come out of it and each is consumed somewhere different.

- **A verdict per model.** A model that fails a required behaviour is not
  selectable for an investigation, and ``require_usable`` is the one gate that
  enforces it, naming the behaviour rather than reporting "unusable".
- **Measured limits.** Usable context and the schema count the model can hold,
  both of which the runtime reads to decide when to compact and how much to
  offer. Where nobody probed, ``UNMEASURED_LIMITS`` keeps the shipped ceilings.
- **A cache.** Keyed on the model's identity and dropped when that identity
  changes, so a model pulled again underneath a running deployment is re-probed
  rather than answered from the old measurement.
"""

from __future__ import annotations

from core.llm.probe.behaviours import (
    REQUIRED_FOR_INVESTIGATION,
    Behaviour,
    BehaviourStatus,
)
from core.llm.probe.cache import ProbeCache
from core.llm.probe.report import (
    UNMEASURED_LIMITS,
    BehaviourResult,
    EndpointProbe,
    ModelIdentity,
    ModelLimits,
    ModelProbe,
    ModelUnusableError,
    require_usable,
)
from core.llm.probe.suite import ProbeTarget, probe_endpoint, probe_model

__all__ = [
    "REQUIRED_FOR_INVESTIGATION",
    "UNMEASURED_LIMITS",
    "Behaviour",
    "BehaviourResult",
    "BehaviourStatus",
    "EndpointProbe",
    "ModelIdentity",
    "ModelLimits",
    "ModelProbe",
    "ModelUnusableError",
    "ProbeCache",
    "ProbeTarget",
    "probe_endpoint",
    "probe_model",
    "require_usable",
]

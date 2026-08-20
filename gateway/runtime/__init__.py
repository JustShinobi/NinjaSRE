"""The first-party investigation runtime a deployment composes.

Everything under this package is the composition root for the canonical
loop: choosing a provider and a capability catalogue, over the credential
proxy binding this process already made at startup.
``factory.build_investigator`` is the no-argument callable an operator names
in the setting that chooses a deployment's investigation runtime.
"""

from __future__ import annotations

from gateway.runtime.factory import build_investigator
from gateway.runtime.investigator import ReActInvestigationRunner

__all__ = ["ReActInvestigationRunner", "build_investigator"]

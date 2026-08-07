"""Argo CD's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Argo CD has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.argocd.tools.failed_runs import argocd_failed_runs
from integrations.argocd.tools.pipeline_statistics import argocd_pipeline_statistics

__all__ = [
    "argocd_failed_runs",
    "argocd_pipeline_statistics",
]

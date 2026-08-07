"""Jenkins's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Jenkins has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.jenkins.tools.failed_runs import jenkins_failed_runs
from integrations.jenkins.tools.pipeline_statistics import jenkins_pipeline_statistics

__all__ = [
    "jenkins_failed_runs",
    "jenkins_pipeline_statistics",
]

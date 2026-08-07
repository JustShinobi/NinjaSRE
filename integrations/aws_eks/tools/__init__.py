"""AWS EKS's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
AWS EKS has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.aws_eks.tools.recent_changes import aws_eks_recent_changes
from integrations.aws_eks.tools.resource_inventory import aws_eks_resource_inventory

__all__ = [
    "aws_eks_recent_changes",
    "aws_eks_resource_inventory",
]

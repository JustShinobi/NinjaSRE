"""AWS's agent-callable capabilities, reading CloudWatch Logs.

Two, and the split is the one CloudWatch forces. Unlike a log store with a
server-side aggregation endpoint, plain CloudWatch Logs can only list groups and
filter events — so "statistics before samples" has to be approximated by
narrowing the group and the window first, and the skill says so rather than
pretending the vendor offers something it does not.

Discovery walks this package, so adding a capability here is one module and no
edit anywhere else.
"""

from __future__ import annotations

from integrations.aws.tools.filter_log_events import aws_filter_log_events
from integrations.aws.tools.list_log_groups import aws_list_log_groups

__all__ = [
    "aws_filter_log_events",
    "aws_list_log_groups",
]

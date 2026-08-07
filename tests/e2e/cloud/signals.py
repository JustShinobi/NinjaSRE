"""Asking the cloud whether the fault this run injected is showing.

The same question the chaos suite asks a cluster, against a provider that has no
cluster to ask. The answer comes from the provider's own alarms, because those
are the thing that already knows "this metric is outside its band" for every
service the suite covers — writing a metric query per scenario would be writing
the alarm's job again, differently, six times.

An alarm the run's own module created is what is read, so this is not depending
on the operator having configured anything: the declarative module brings the
alarm up beside the infrastructure it watches, and it goes when the stack goes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from config.constants.chaos import CLOUD_RUN_TAG_KEY
from tests.chaos.framework.cluster import ProbeReading
from tests.support.commands import CommandRunner

#: What each probe name means in terms of the provider's alarm state. The
#: translation lives here rather than in a scenario document, so a scenario
#: names a probe and this decides how to read it.
PROBE_SYMPTOMS: Mapping[str, tuple[str, ...]] = {
    "cluster_capacity_below_desired": ("pods_pending", "node_count_dropped"),
    "target_group_has_unhealthy_targets": ("target_unhealthy", "instance_state_changed"),
    "alarm_state_is_not_ok": ("alarm_in_insufficient_data", "metric_gap"),
    "function_error_rate_above_threshold": ("invocation_errors_rising", "duration_at_limit"),
    "service_below_desired_count": ("tasks_pending", "service_below_desired_count"),
    "database_connections_at_limit": (
        "connections_at_limit",
        "application_connection_errors",
    ),
}

#: The alarm states that mean the fault is showing. ``INSUFFICIENT_DATA`` counts,
#: because a metric that stopped being published is exactly what one of the
#: scenarios injects — treating it as "no symptom" would report that scenario
#: invalid every time it worked.
FIRING_STATES: frozenset[str] = frozenset({"ALARM", "INSUFFICIENT_DATA"})


@dataclass(frozen=True, slots=True)
class CloudSignals:
    """Reads the provider's alarms for one run, and answers in symptom names."""

    runner: CommandRunner
    run_id: str
    region: str = "eu-west-1"
    binary: str = "aws"
    symptoms: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: PROBE_SYMPTOMS)

    def observe(self, probe: str, *, namespace: str = "") -> ProbeReading:
        """Return the symptoms ``probe`` can see right now."""
        declared = self.symptoms.get(probe)
        if declared is None:
            return ProbeReading(
                probe=probe,
                detail=(
                    f"no implementation for cloud probe {probe!r}; the run is reported as "
                    f"inconclusive rather than scored against a symptom nobody read"
                ),
            )

        result = self.runner.run(
            (
                self.binary,
                "cloudwatch",
                "describe-alarms",
                "--alarm-name-prefix",
                f"{CLOUD_RUN_TAG_KEY.replace(':', '-')}-{self.run_id}",
                "--region",
                self.region,
                "--output",
                "json",
            ),
            timeout=60.0,
        )
        if not result.ok:
            return ProbeReading(probe=probe, detail=result.message)

        try:
            document = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as failure:
            return ProbeReading(probe=probe, detail=f"the alarm listing was not JSON: {failure}")

        states = {
            str(alarm.get("StateValue", ""))
            for alarm in document.get("MetricAlarms") or ()
            if isinstance(alarm, Mapping)
        }
        if not states:
            return ProbeReading(probe=probe, detail="this run created no alarms to read")
        if states & FIRING_STATES:
            return ProbeReading(probe=probe, observed=declared, detail=", ".join(sorted(states)))
        return ProbeReading(probe=probe, observed=(), detail=", ".join(sorted(states)))


__all__ = ["FIRING_STATES", "PROBE_SYMPTOMS", "CloudSignals"]

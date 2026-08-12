"""What it costs to read somebody else's monitoring, and how much of it is read.

The deployment already bounds its *own* watching in
``config.constants.observation``. These are the bounds on the other half — the
metrics, logs and dashboards an operator was already running before this system
arrived. They are a different kind of number and that is why they are a
different module: every bound here protects a system this deployment does not
own and cannot restart.

Three groups.

**How much of a metrics system is looked at.** A homelab Prometheus holds tens
of thousands of series and a mapping pass that enumerated all of them would be
the most expensive thing the deployment does, once a minute, for the sake of a
join that changes when the estate changes. So mapping is bounded, runs on a
schedule rather than per query, and reports what it did not reach.

**How far back history is read.** A detector reading history from the source
rather than from the deployment's own samples is the whole of why the bridge
earns its place — it can conclude something about a window nobody was polling
during. The lookback is bounded because "read everything Prometheus has" is a
query that can take a metrics system down, and taking the operator's monitoring
down is the one failure this feature must never cause.

**How much of a log stream is returned.** Every log query states its bound in
its own result. An answer that was truncated and did not say so is worse than
no answer, because the reader draws a conclusion from it.
"""

from __future__ import annotations

from typing import Final

# --- Sources -----------------------------------------------------------------------

#: The signal source name every reading that came from the bridge carries. One
#: string, so a console showing provenance, a precedence rule, and the stored
#: signal all spell it the same way.
BRIDGE_SOURCE: Final = "observability-bridge"

#: What a precedence rule names when the operator's metrics system wins.
PRECEDENCE_SOURCE_BRIDGE: Final = "bridge"

#: What it names when the deployment's own polling wins.
PRECEDENCE_SOURCE_POLLING: Final = "polling"

#: The two answers a precedence rule may give. There is no third: "both" is the
#: outcome the rule exists to prevent, and "neither" is a detector nobody is
#: feeding.
PRECEDENCE_SOURCES: Final[tuple[str, ...]] = (
    PRECEDENCE_SOURCE_BRIDGE,
    PRECEDENCE_SOURCE_POLLING,
)

#: Precedence rules one deployment may declare. Past this the operator has a
#: routing table rather than a handful of decisions about duplicated coverage.
MAX_PRECEDENCE_RULES: Final[int] = 100

#: Whose account of a resource a series is, as configuration spells them.
#: Repeated here rather than imported from the enum because ``config/`` imports
#: nothing first-party — the tier rule, and also what lets the schema validate a
#: document without loading the mapping engine.
BRIDGE_VIEW_HYPERVISOR: Final = "hypervisor"
BRIDGE_VIEW_NODE: Final = "node"
BRIDGE_VIEW_GUEST: Final = "guest"
BRIDGE_VIEWS: Final[tuple[str, ...]] = (
    BRIDGE_VIEW_HYPERVISOR,
    BRIDGE_VIEW_NODE,
    BRIDGE_VIEW_GUEST,
)

# --- Mapping -----------------------------------------------------------------------

#: Series one mapping pass may associate with estate resources. A metrics system
#: with a million series is ordinary; a join over a million series once a minute
#: is not, and the bound is what keeps the pass finishable rather than merely
#: slow.
MAX_MAPPED_SERIES: Final[int] = 5_000

#: Unmapped series reported with their labels. Reporting *all* of them would
#: mean a deployment pointed at an unconfigured Prometheus produced a report
#: nobody can read; reporting none would make a mapping gap silent, which is
#: the failure this reporting exists to prevent. A sample plus a total is the
#: honest middle.
MAX_UNMAPPED_REPORTED: Final[int] = 200

#: Series one resource may expose to an investigation. An investigation asking
#: for "this guest's metrics" wants the ones that describe it, not every series
#: whose labels happen to mention it.
MAX_SERIES_PER_RESOURCE: Final[int] = 100

#: Label rules one deployment may declare, shipped defaults included.
MAX_LABEL_RULES: Final[int] = 200

#: How often the series-to-resource mapping is rebuilt. Not per query: the join
#: changes when the estate changes or when a target is added, both of which are
#: minute-scale events, and rebuilding it per detector evaluation would multiply
#: the cost by the detector count for no new information.
DEFAULT_MAPPING_INTERVAL_SECONDS: Final[int] = 300

#: The shortest mapping interval an operator may configure. Below this the pass
#: overlaps itself on an estate of any size.
MIN_MAPPING_INTERVAL_SECONDS: Final[int] = 60

#: The job kind the scheduler stores for one mapping pass.
BRIDGE_MAPPING_JOB_KIND: Final = "observability.mapping"

# --- History -----------------------------------------------------------------------

#: How far back a history-backed source reads when nothing says otherwise. An
#: hour: long enough that a detector restarted five minutes ago still has the
#: window it needs, short enough that the query is cheap on a homelab.
DEFAULT_HISTORY_LOOKBACK_SECONDS: Final[int] = 3_600

#: The furthest back one history read may reach. "Read everything Prometheus
#: has" is a query that can take a metrics system down, and taking the
#: operator's own monitoring down is the one failure this feature must not
#: cause.
MAX_HISTORY_LOOKBACK_SECONDS: Final[int] = 86_400

#: The resolution a history read asks for. Matched to the default poll interval
#: so a window filled from history and a window filled from polling have samples
#: at the same spacing — a detector's duration arithmetic reads the interval off
#: the sample, and two spacings for one signal would make it wrong for one of
#: them.
DEFAULT_HISTORY_STEP_SECONDS: Final[int] = 60

#: Samples one history read may return per series. A day at a minute's
#: resolution is 1,440, so this is the day-long read plus room for a finer step.
MAX_HISTORY_SAMPLES: Final[int] = 2_000

# --- Logs --------------------------------------------------------------------------

#: What the capability that reads a resource's logs is called. Named after the
#: question it answers rather than the vendor that answers it, because a
#: deployment may change log systems and an investigation should not notice.
LOGS_TOOL_NAME: Final[str] = "logs_for_resource"

#: What a log evidence entry's reference is prefixed with, so a conclusion drawn
#: from lines can be followed back to the exact query and window that read them.
LOG_REFERENCE_PREFIX: Final[str] = "log"

#: Lines one log query returns. The bound is stated in the result rather than
#: applied silently: an answer that was truncated and did not say so is worse
#: than no answer, because the reader draws a conclusion from it.
MAX_LOG_LINES: Final[int] = 500

#: The window a log query covers when the caller names none.
DEFAULT_LOG_WINDOW_SECONDS: Final[int] = 900

#: The longest window one log query may cover.
MAX_LOG_WINDOW_SECONDS: Final[int] = 86_400

# --- Dashboards --------------------------------------------------------------------

#: How much time a dashboard link adds either side of the incident's window. A
#: panel that starts exactly at the firing instant shows a cliff with nothing
#: before it, and the minutes before are what tell an operator whether it was a
#: step or a climb.
DASHBOARD_LINK_PADDING_SECONDS: Final[int] = 600

#: Dashboard mappings one deployment may declare.
MAX_DASHBOARD_MAPPINGS: Final[int] = 100

# --- Exporters ---------------------------------------------------------------------

#: The estate source whose native identifiers the shipped rules address. The
#: integration's own name, repeated here because ``config/`` imports nothing
#: first-party and the shipped rules are read by tier 3, which cannot import the
#: integration that owns the string either.
PROXMOX_ESTATE_SOURCE: Final = "proxmox"

#: The exporter that publishes a Proxmox cluster's own view of itself.
EXPORTER_PROXMOX: Final = "prometheus-pve-exporter"

#: The exporter that publishes a machine's view of itself.
EXPORTER_NODE: Final = "node-exporter"

#: The publication path for a reading with no exporter of its own: a file a
#: script writes and the node exporter serves. Named because it is a supported
#: path rather than a workaround — it is how the readings that explain a
#: hypervisor outage reach this system at all.
EXPORTER_TEXTFILE: Final = "node-exporter-textfile"

__all__ = [
    "BRIDGE_MAPPING_JOB_KIND",
    "BRIDGE_SOURCE",
    "BRIDGE_VIEWS",
    "BRIDGE_VIEW_GUEST",
    "BRIDGE_VIEW_HYPERVISOR",
    "BRIDGE_VIEW_NODE",
    "DASHBOARD_LINK_PADDING_SECONDS",
    "DEFAULT_HISTORY_LOOKBACK_SECONDS",
    "DEFAULT_HISTORY_STEP_SECONDS",
    "DEFAULT_LOG_WINDOW_SECONDS",
    "DEFAULT_MAPPING_INTERVAL_SECONDS",
    "EXPORTER_NODE",
    "EXPORTER_PROXMOX",
    "EXPORTER_TEXTFILE",
    "MAX_DASHBOARD_MAPPINGS",
    "MAX_HISTORY_LOOKBACK_SECONDS",
    "MAX_HISTORY_SAMPLES",
    "MAX_LABEL_RULES",
    "LOGS_TOOL_NAME",
    "LOG_REFERENCE_PREFIX",
    "MAX_LOG_LINES",
    "MAX_LOG_WINDOW_SECONDS",
    "MAX_MAPPED_SERIES",
    "MAX_PRECEDENCE_RULES",
    "MAX_SERIES_PER_RESOURCE",
    "MAX_UNMAPPED_REPORTED",
    "MIN_MAPPING_INTERVAL_SECONDS",
    "PRECEDENCE_SOURCES",
    "PRECEDENCE_SOURCE_BRIDGE",
    "PRECEDENCE_SOURCE_POLLING",
    "PROXMOX_ESTATE_SOURCE",
]

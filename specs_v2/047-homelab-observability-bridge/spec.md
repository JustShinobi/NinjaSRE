# Feature 047 — Homelab Observability Bridge

- **Wave:** 11 — Proxmox and the homelab
- **Branch:** `feat/047-homelab-observability-bridge`
- **Status:** Draft
- **Depends on:** 038, 039, 044

## Summary

Wiring the observability stack a homelab already runs — Prometheus, Grafana,
Alertmanager, Loki — to the estate, the signal store and the incident lifecycle,
so that the metrics and logs already being collected become the system's eyes
rather than a second place to look.

The integrations exist: `prometheus`, `grafana`, `alertmanager`, `loki`,
`victoriametrics`, `victorialogs` are all in the tree with real clients. What
does not exist is the join. A Prometheus series is not connected to an estate
resource, an Alertmanager alert becomes a run rather than an incident, a Grafana
dashboard is a link nobody follows, and a Loki query is something the agent might
think to make rather than something the investigation reaches for.

This feature makes that join, and adds the piece a Proxmox homelab specifically
needs: the exporter metrics that describe a hypervisor, mapped to the resources
they describe.

## User scenarios

### Primary story

An operator already runs Prometheus with the Proxmox exporter and node exporter,
and Grafana on top. They point the deployment at Prometheus once. Their existing
metrics become signals against the estate resources they describe — this series
is that virtual machine — so detectors can be written against real history rather
than against polls the system makes itself.

Their existing Alertmanager alerts arrive as incidents, correlated to the same
resources, alongside the ones the system detects itself. An investigation into a
guest pulls that guest's metrics and its logs from Loki without being told where
they are.

And when the report is written, it links to the Grafana panel showing the window
in question, so the operator sees the picture rather than a number.

### Acceptance scenarios

1. **Given** a Prometheus endpoint, **when** it is configured, **then** it is
   verified by a real query, and the verification reports which of the expected
   exporters are present.
2. **Given** a metric series and the estate, **when** mapping runs, **then**
   series are associated with the resources they describe, through declared
   label rules, and unmapped series are reported rather than dropped.
3. **Given** a mapped series, **when** a detector reads it, **then** it reads
   history from Prometheus rather than only the samples the deployment polled.
4. **Given** an Alertmanager alert, **when** it arrives, **then** it produces an
   incident through feature 039's single lifecycle, correlated to the estate
   resource it names.
5. **Given** an Alertmanager alert that resolves, **when** the resolution
   arrives, **then** the incident closes, recording that the source resolved it.
6. **Given** an investigation into a resource, **when** it gathers evidence,
   **then** that resource's metrics and its logs are reachable without the agent
   having to know the query language of either.
7. **Given** a Grafana instance, **when** a report is produced, **then** it links
   to the dashboard and time window relevant to the incident, where one is
   mapped.
8. **Given** a metrics endpoint that is down, **when** detectors depend on it,
   **then** that is itself raised, and the detectors report as unable to
   evaluate rather than as finding nothing wrong.
9. **Given** a homelab with no observability stack at all, **when** the
   deployment runs, **then** everything still works from the deployment's own
   polling; this feature is additive.
10. **Given** both a Prometheus signal and the deployment's own poll for the same
    thing, **when** both exist, **then** the duplication is resolved by a declared
    precedence, not by both firing.

### Edge cases

- A Prometheus with no Proxmox exporter but a node exporter.
- Metrics whose labels do not identify a resource the estate holds.
- A guest that exists in metrics after being destroyed.
- Two Prometheus instances covering overlapping targets.
- An Alertmanager alert naming a resource the estate does not know.
- Loki with a retention shorter than the investigation's window.
- A Grafana instance behind authentication the deployment does not hold.
- Metric cardinality large enough that mapping is expensive.
- A homelab where Prometheus itself runs as a guest on the cluster it monitors.

## Requirements

### Functional

**Metrics**

- **FR-001** A metrics source MUST be configurable and verifiable by a real
  query, reporting which expected exporters are present.
- **FR-002** Series MUST be mapped to estate resources through declared label
  rules, configurable per deployment.
- **FR-003** Unmapped series MUST be reported, with their labels, so a mapping
  gap is visible rather than silent.
- **FR-004** A resource MUST expose the series mapped to it, so an investigation
  can ask for "this guest's metrics" without composing a query.
- **FR-005** Detectors MUST be able to read history from the metrics source, not
  only the deployment's own samples.
- **FR-006** Where the deployment polls for something the metrics source also
  provides, precedence MUST be declared, and only one MUST produce signals.
- **FR-007** A metrics source that is unavailable MUST raise that fact, and
  dependent detectors MUST report inability to evaluate, never absence of
  problems.

**Alerts**

- **FR-008** Alertmanager alerts MUST arrive as incidents through feature 039's
  lifecycle, with no second path.
- **FR-009** An alert MUST be correlated to the estate resource it names, and an
  alert naming an unknown resource MUST still open an incident, marked as
  uncorrelated.
- **FR-010** An alert resolution MUST close its incident, recorded as
  source-resolved.
- **FR-011** Alert grouping from the source MUST be respected rather than
  re-derived.

**Logs**

- **FR-012** A log source MUST be configurable and verifiable.
- **FR-013** A resource MUST expose the log stream selector that applies to it,
  so an investigation can ask for "this guest's logs".
- **FR-014** Log queries MUST be bounded in time and in returned volume, and the
  bound MUST be stated in the result.
- **FR-015** A log source whose retention is shorter than the requested window
  MUST say so rather than returning a partial answer as if complete.

**Dashboards**

- **FR-016** A dashboard MUST be mappable to a resource kind or a detector, so a
  report can link to the relevant panel and time window.
- **FR-017** A link MUST carry the incident's time window.
- **FR-018** Where no dashboard is mapped, the report MUST omit the link rather
  than linking to a default.

**Proxmox specifics**

- **FR-019** The Proxmox exporter's metric names MUST have a declared mapping to
  estate resource kinds, shipped rather than configured. The reference cluster
  already runs `prometheus-pve-exporter`, so this mapping has a concrete target
  rather than a hypothetical one.
- **FR-019a** Existing alert rules MUST be honoured rather than duplicated. Where
  a deployment already has a rule covering a condition a shipped detector also
  covers, the precedence rule of FR-006 applies and the duplication MUST be
  reported to the operator with both definitions shown. The reference cluster
  already carries four rule files, and a system that silently double-alerts on
  conditions it did not author will be turned off.
- **FR-019c** The bridge MUST carry the readings the Proxmox REST API cannot
  answer and feature 044 therefore delegates here: failed `systemd` units, bridge
  presence and state, and LVM thin-pool metadata usage. Where a node publishes no
  exporter for them, the bridge MUST report them **unavailable** and name what
  would publish them — never absent, and never healthy.
- **FR-019d** A textfile collector MUST be a supported publication path for
  readings with no exporter of their own. This is how the reference cluster's own
  operators solved the quorum-visibility gap their postmortem identified, and
  reinventing the mechanism beside theirs would give the node two.
- **FR-019b** The bridge MUST detect and report when the metrics source is hosted
  **inside the estate it observes**, naming the resources involved. In the
  reference cluster the entire stack — Prometheus, Alertmanager, Grafana, the
  blackbox exporter and Loki — runs as containers on one node, and during that
  cluster's only total outage not one alert fired.
- **FR-020** Node exporter metrics MUST be mappable to Proxmox node resources.
- **FR-021** Where a guest exposes its own exporter, it MUST be mappable to the
  guest resource, and the guest's own view MUST be distinguishable from the
  hypervisor's view of it.

**Optionality**

- **FR-022** Every part of this feature MUST be optional. A deployment with no
  observability stack MUST function fully on its own polling.
- **FR-023** Enabling a source MUST NOT silently change which detectors fire; the
  change in signal provenance MUST be visible.

### Non-functional

- **NFR-001** Mapping MUST be bounded and MUST not enumerate high-cardinality
  label sets exhaustively.
- **NFR-002** Metric and log queries MUST respect the source's rate limits and
  MUST go through the credential proxy.
- **NFR-003** A slow or unavailable source MUST NOT delay an investigation beyond
  its declared budget.
- **NFR-004** Nothing here may become a required dependency of features 038, 039
  or 044.

## Success criteria

- **SC-001** Verification against a real Prometheus reports which expected
  exporters are present.
- **SC-002** Series map to estate resources through label rules; unmapped series
  are reported with their labels.
- **SC-003** A detector reads history from the metrics source and fires on a
  condition the deployment's own polling had not sampled.
- **SC-004** An Alertmanager alert and a detected condition produce structurally
  identical incidents.
- **SC-005** An alert resolution closes its incident as source-resolved.
- **SC-006** An investigation retrieves a resource's metrics and logs without
  composing a query.
- **SC-007** A report links to the mapped dashboard with the incident's window,
  and omits the link when none is mapped.
- **SC-008** An unavailable metrics source raises, and dependent detectors report
  inability to evaluate.
- **SC-009** A deployment with no observability stack passes the full suite.
- **SC-010** Duplicate coverage resolves by declared precedence, with one source
  producing signals.

## Out of scope

- Deploying or configuring Prometheus, Grafana, Alertmanager or Loki.
- Writing dashboards. The existing `deploy/dashboards/` set is unchanged.
- Long-term metric storage inside the deployment.

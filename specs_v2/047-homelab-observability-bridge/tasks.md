# Tasks — 046 Homelab Observability Bridge

## Phase 1 — Metrics source

- **T-001** Metrics source configuration; verification by a real query.
- **T-002** Failing test: verification reports which expected exporters are
  present, and names the absent ones.
- **T-003** Queries through the credential proxy with the integration's existing
  rate limiting; structural test that no credential is held.

## Phase 2 — Mapping

- **T-004** Declared label-rule format, configurable per deployment.
- **T-005** Shipped default mappings for the Proxmox exporter and the node
  exporter to estate resource kinds.
- **T-006** Failing test: series map to the resources they describe; a guest
  series lands on the guest resource.
- **T-007** Failing test: unmapped series are reported with their labels, not
  dropped.
- **T-008** Resource-to-series exposure, so an investigation asks for "this
  guest's metrics" without composing a query.
- **T-009** Bounded mapping over a high-cardinality label set; mapping runs on a
  schedule, not per query.
- **T-010** A guest present in metrics after being destroyed maps to the absent
  resource, not to a new one.

## Phase 3 — History-backed detectors

- **T-011** Detectors reading history from the metrics source.
- **T-012** Failing test: a detector fires on a condition present in Prometheus
  history that the deployment's own polling had not sampled.
- **T-013** Declared precedence between source and own polling; failing test that
  only one produces signals for a duplicated coverage.
- **T-014** Failing test: an unavailable metrics source raises, and dependent
  detectors report inability to evaluate rather than absence of problems.

## Phase 4 — Alerts

- **T-015** Alertmanager alerts through feature 039's lifecycle; assert no second
  path exists.
- **T-016** Failing test: an Alertmanager alert and a detected condition produce
  structurally identical incidents.
- **T-017** Correlation to the estate resource named; an alert naming an unknown
  resource opens an incident marked uncorrelated.
- **T-018** Failing test: an alert resolution closes its incident as
  source-resolved.
- **T-019** Source grouping respected rather than re-derived.

## Phase 5 — Logs

- **T-020** Log source configuration and verification.
- **T-021** Per-resource stream selectors; an investigation asks for "this
  guest's logs".
- **T-022** Bounded queries in time and volume, with the bound stated in the
  result.
- **T-023** Failing test: a retention shorter than the requested window is stated,
  not returned as a complete answer.

## Phase 6 — Dashboards

- **T-024** Dashboard mapping to resource kinds and detectors.
- **T-025** Report links carrying the incident's time window.
- **T-026** Failing test: no mapped dashboard means no link, never a default one.
- **T-027** A Grafana instance behind unavailable authentication degrades to no
  link with the reason recorded.

## Phase 7 — Optionality

- **T-028** Failing test: the full suite passes with no observability stack
  configured.
- **T-029** Enabling a source makes the change in signal provenance visible;
  assert it does not silently change which detectors fire.
- **T-030** Assert features 038, 039 and 045 have no hard dependency on this one.

## Definition of done

- SC-001 through SC-010 each proven by a named test.
- Shipped exporter mappings verified against a real Proxmox exporter.
- `make verify` green.

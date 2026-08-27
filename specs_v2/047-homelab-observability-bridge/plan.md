# Plan — 046 Homelab Observability Bridge

## Technical context

| Concern | Choice |
|---|---|
| Location | A bridge module in `platform/observation/sources/`, using the existing `integrations/prometheus`, `grafana`, `alertmanager`, `loki` clients |
| Mapping | Declared label rules in configuration, with a shipped default set for the Proxmox and node exporters |
| Alert path | The existing `/webhooks/alertmanager` route, rewired by feature 039 to raise incidents |
| Queries | Through the credential proxy, rate-limited by the existing integration base |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | An unavailable source must not read as "nothing wrong". | FR-007: a source that is down raises, and dependent detectors report inability to evaluate. This is the failure mode that makes monitoring dangerous. |
| III — Read-only by default | Everything here reads. | Queries only. No dashboard is written, no alert is silenced at the source. |
| IV — Secrets never reach the agent | Prometheus and Grafana may be authenticated. | Credentials in the vault, injected by the proxy. |
| VIII — Layered architecture | A platform module over tier-2 integrations. | The bridge depends on the integration clients through the capability registry, and on `platform/estate/` and `platform/observation/`. |
| XI — Single datastore | Metrics could be copied in. | Refused. The bridge queries the source; only derived signals that a detector actually uses are stored, under the existing retention. |

## Architecture decisions

**Query the source; do not copy it.** Prometheus is already a time-series
database with retention the operator chose. Ingesting its series into Postgres
would duplicate storage, halve retention and add a synchronisation problem.
Detectors read history through the source, and only the signals they derive land
in the signal store.

**Mapping is by declared label rules, with shipped defaults.** Associating a
series with a resource is the whole value of the feature and is entirely
deployment-specific — except for the exporters everyone runs, whose label schemes
are stable. Shipping the Proxmox and node exporter mappings means the common case
needs no configuration, and the rules are visible and overridable for everything
else.

**Unmapped is reported, not dropped.** A silent mapping gap is a metric the
operator believes is being watched and is not. Reporting unmapped series with
their labels turns configuring the bridge into an iterative, visible task.

**One incident lifecycle, again.** Alertmanager alerts go through feature 039's
lifecycle, not a parallel one. SC-004 asserts structural identity. This is the
same decision feature 039 made for webhooks generally, restated here because
Alertmanager is the source most likely to tempt a shortcut.

**Precedence, not both.** When Prometheus and the deployment's own poller both
cover a datastore's fullness, two detectors firing on one condition produce two
incidents about one problem. Precedence is declared per signal, and the losing
source stops producing rather than producing and being filtered.

**Everything is optional.** NFR-004 is load-bearing: a homelab with no
observability stack is the common case, and the deployment's own polling must
remain sufficient. This feature is a bridge, not a foundation.

## Phases

1. **Metrics source.** Configuration, real-query verification, exporter presence
   reporting, credential proxy, rate limits.
2. **Mapping.** Declared label rules, shipped Proxmox and node exporter defaults,
   unmapped reporting, bounded cardinality handling, resource-to-series exposure.
3. **History-backed detectors.** Detectors reading from the source; precedence
   between source and own polling; unavailability raising and detector
   inability-to-evaluate.
4. **Alerts.** Alertmanager to incident through the one lifecycle; correlation to
   resources; uncorrelated alerts still opening; resolution closing; source
   grouping respected.
5. **Logs.** Configuration and verification; per-resource stream selectors;
   bounded queries with the bound stated; retention-shorter-than-window honesty.
6. **Dashboards.** Mapping to kinds and detectors; links carrying the incident
   window; omission when unmapped.
7. **Optionality.** The full suite passing with no observability stack
   configured; provenance visibility when a source is enabled.

## Risks

- **Mapping rules become an unmaintainable per-deployment burden.** Mitigated by
  shipping the defaults for the exporters a Proxmox homelab actually runs, so most
  operators configure nothing.
- **Prometheus running as a guest on the cluster it monitors disappears exactly
  when needed.** Mitigated by FR-007 and by the deployment's own polling remaining
  active for the signals it can gather directly — which is why precedence is
  per-signal rather than per-source.
- **High-cardinality mapping is expensive.** Mitigated by NFR-001's bound and by
  mapping on a schedule rather than per query.

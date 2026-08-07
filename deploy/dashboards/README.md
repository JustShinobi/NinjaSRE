# Reference dashboards

Two files, for the stack most operators already run. Import them, point them at
the Prometheus that scrapes your collector, and you have every metric this
deployment can emit without building a panel.

- `grafana-ninjasre.json` — one row per metric family, one panel per instrument.
- `prometheus-rules.yml` — the four ratios worth recording and the five
  conditions worth an alert.

## Before either is useful

Nothing is exported until you say where to. Set one variable:

```sh
NINJASRE_OTEL_ENDPOINT=http://otel-collector:4318
```

That is an OTLP/HTTP base URL. Traces go to `/v1/traces`, metrics to
`/v1/metrics`, and logs to `/v1/logs` — the paths the protocol fixes, so one
setting covers all three. Unset, nothing leaves the host and these dashboards
stay empty, which is the default and is not a fault.

Two optional companions:

```sh
NINJASRE_TELEMETRY_SERVICE_NAME=ninjasre        # what the collector calls you
NINJASRE_TELEMETRY_SAMPLE_RATIO=1.0             # lower it if tracing shows up in latency
```

## Importing

**Grafana** — Dashboards → New → Import → *Upload JSON file* →
`grafana-ninjasre.json`, then pick your Prometheus data source when it asks.
The dashboard has no hard-coded data source UID, so it works against whichever
one you choose.

**Prometheus** — put `prometheus-rules.yml` wherever your `rule_files` glob
points and reload. If you run the Prometheus Operator, the same content fits a
`PrometheusRule` resource with `groups` moved under `spec`.

## Metric names

The panels query the Prometheus form of each instrument: dots become
underscores and a counter gains `_total`, which is what the collector's
Prometheus exporter produces. Every panel's description names the OTLP
instrument it came from, so the two can be matched by eye.

## Thresholds

The alert thresholds are starting points. They depend entirely on how much you
investigate and with what, and a threshold copied from another deployment is an
alert nobody trusts by the second week. Run for a fortnight, look at the
recording rules, then set them from your own numbers.

## Cardinality

Every label these dashboards group by is allow-listed at the instrument, and
each one is capped at 200 distinct values before further ones collapse into an
`__overflow__` bucket. A panel that shows `__overflow__` climbing is telling you
a label is being used for something unbounded — that is a bug worth reporting,
not a threshold to raise.

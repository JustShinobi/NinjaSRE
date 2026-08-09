"""The join between the monitoring an operator already runs and this deployment.

Most estates that need an SRE already have Prometheus, Grafana, Alertmanager and
Loki. What they do not have is a connection between a metric series and the
thing it measures, between somebody else's alert and this system's incident
lifecycle, or between an investigation and the logs of the guest it is about.
This package is that connection and nothing else: it collects no metrics, stores
no series, writes no dashboard and silences no alert.

Four properties hold across every module here.

**It queries; it does not copy.** Prometheus is already a time-series database
with retention the operator chose. Ingesting its series would halve that
retention, double the storage and add a synchronisation problem, so detectors
read history *through* the source and only the signals they derive are stored.

**It is entirely optional.** A deployment with no observability stack works from
its own polling and passes the whole suite. Nothing in ``platform/estate``,
``platform/observation`` or ``platform/incidents`` imports this package, and a
test asserts that rather than trusting it.

**A source that cannot be reached says so.** The failure mode that makes
monitoring dangerous is looking healthy because it stopped looking. An
unreachable metrics source raises, and every detector that depended on it reports
that it could not be evaluated — never that nothing is wrong.

**It holds no credential.** Every provider is reached through a protocol here and
an integration client behind it, which lets the credential proxy inject the
secret at the network edge. There is no parameter in this package a token fits
in, and a structural test walks the whole package to keep it that way.
"""

from __future__ import annotations

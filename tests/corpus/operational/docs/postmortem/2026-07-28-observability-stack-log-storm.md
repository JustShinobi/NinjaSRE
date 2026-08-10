# The observability stack took itself down with its own logs

A validation run against the telemetry store produced more log volume than the
telemetry store could ingest.

## Symptom

Query latency on the telemetry store rose from milliseconds to tens of seconds,
then the ingest pipeline stopped accepting writes. Dashboards went blank.

## Investigation

The system log table was growing faster than any application table. The
validation run enables verbose query logging, and the store writes its own
query log through its own ingest path, so each logged query produced further
logged queries.

## Root cause

Verbose query logging on a store that ingests its own logs is a feedback loop.
Nothing bounded it because the log volume was accounted as application traffic.

## Correction

Turned verbose query logging off outside a validation window and gave the
system log table its own retention. Added a detector on ingest lag.

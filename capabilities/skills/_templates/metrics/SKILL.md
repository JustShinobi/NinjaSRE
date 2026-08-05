---
name: metrics-VENDOR
display_name: VENDOR metric investigation
description: Time-series investigation. Percentiles and grouping before averages.
domain: metrics
applies_when:
  alert_sources: [VENDOR]
  tags: [metrics, latency, saturation, throughput]
directs_tools:
  - VENDOR_query_metrics
  - VENDOR_list_monitors
requires:
  integrations: [VENDOR]
---

# VENDOR metric investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Bound the window to the symptom, plus normal.** A window starting when
   the alert fired hides the onset, which is the most informative moment.
2. **Read a percentile, not a mean.** An average is fine while the p99 is
   not, and users experience the tail.
3. **Group before concluding.** One bad host inside a healthy fleet average
   is invisible until the series is split.
4. **Check the metric measures the failing path.** A success rate counted
   over responses looks healthy while requests time out before responding.

## What this is not for

- Explaining *why* something changed. Metrics establish that, and when.
- Anything that needs a specific error message.

## Notes for this vendor

- The resolution, and where it degrades with age.
- Which aggregations this vendor computes server-side.
- The delay between an event and its appearance in a series.

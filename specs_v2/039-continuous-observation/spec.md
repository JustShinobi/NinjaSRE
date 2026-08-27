# Feature 039 — Continuous Observation and Incident Lifecycle

- **Wave:** 10 — Autonomous operation
- **Branch:** `feat/039-continuous-observation`
- **Status:** Draft
- **Depends on:** 038

## Summary

The component that makes the system speak first. It watches the estate, decides
that something is wrong, and opens an incident — without a webhook, without a
cron entry somebody wrote by hand, and without a human noticing anything.

Today an investigation begins in exactly two ways: an alert arrives at
`/webhooks/*`, or a scheduled job fires with an objective a person typed. Both
assume an upstream that already knows something is wrong. A homelab has no such
upstream. Neither does most infrastructure before somebody builds one, which is
why "we would have caught it if we had an alert for it" is the most common
sentence in a post-incident review.

This feature adds the third way: a detector observes signals over time, applies a
rule, and raises. It also adds the noun that investigation results attach to —
the incident — with a lifecycle that opens, correlates, escalates and closes.

## User scenarios

### Primary story

Nobody is watching. A datastore crosses ninety per cent used and keeps climbing.
Four minutes later the deployment has opened an incident naming the datastore,
the trend that triggered it, and the guests that would be affected; started an
investigation; and — depending on policy — either fixed it or asked. The operator
learns about it from a notification that includes what has already been done.

The next morning, the same datastore is briefly at ninety-one per cent during a
backup window and nothing happens at all, because that window is declared and the
detector knows it.

### Acceptance scenarios

1. **Given** a detector and a signal crossing its condition, **when** the
   condition holds for its declared duration, **then** an incident is opened
   naming the resource, the signal, the values, and the rule.
2. **Given** a signal that crosses and immediately recovers, **when** the
   duration has not elapsed, **then** nothing is opened.
3. **Given** an open incident for a resource and signal, **when** the same
   condition fires again, **then** it correlates to the existing incident rather
   than opening a second.
4. **Given** an incident whose condition has cleared, **when** the recovery holds
   for its declared duration, **then** the incident closes itself and records
   that it self-resolved.
5. **Given** a declared maintenance window, **when** a condition fires inside it,
   **then** it is suppressed and recorded as suppressed, not discarded silently.
6. **Given** a detector that would fire on fifty resources at once, **when** it
   does, **then** they are grouped into one incident with fifty subjects, not
   fifty incidents.
7. **Given** an incident, **when** it opens, **then** an investigation starts
   with an objective derived from the incident, and the run links back to it.
8. **Given** an incident nobody has addressed, **when** its escalation interval
   elapses, **then** it escalates through the existing escalation registry, and
   escalation stops when the incident closes.
9. **Given** an alert arriving on a webhook, **when** it is ingested, **then** it
   produces an incident through the same lifecycle as a detected one — there MUST
   NOT be two kinds of incident.
10. **Given** a detector that is failing to evaluate, **when** it fails, **then**
    the failure is itself surfaced; a detector that has stopped working MUST NOT
    look like an absence of problems.
11. **Given** a flapping signal, **when** it crosses repeatedly, **then**
    hysteresis prevents an incident per crossing and the flapping itself is
    reported.

### Edge cases

- The observer restarting mid-evaluation.
- Two replicas evaluating the same detector.
- A signal source that stops reporting — distinguishable from a signal reporting
  a good value.
- A resource going absent while an incident about it is open.
- A detector on a resource kind no resource currently has.
- A ten-thousand-resource estate evaluated on every tick.
- Clock skew, and a maintenance window spanning a daylight-saving change.
- An incident open across a deployment upgrade.

## Requirements

### Functional

**Signals**

- **FR-001** A signal MUST be a named, typed, time-stamped value about a resource,
  from a declared source.
- **FR-002** Signal sources MUST include, at minimum: a poller that calls an
  integration on an interval, the estate's own health transitions, and an
  external metrics query.
- **FR-003** A signal that stops arriving MUST be distinguishable from a signal
  reporting a healthy value, and detectors MUST be able to fire on the former.
- **FR-004** Signals MUST be retained long enough to evaluate every detector's
  longest window, and no longer by default.

**Detectors**

- **FR-005** A detector MUST declare: the resource kinds it applies to, the
  signal it reads, its condition, the duration the condition must hold, its
  recovery condition and duration, its severity, and its grouping key.
- **FR-006** Detectors MUST be declarable as configuration, resolvable through
  the hierarchical config service, so a team can add one without new code.
- **FR-007** Condition kinds MUST include at minimum: threshold, absence,
  rate of change, and state transition.
- **FR-008** A detector MUST support hysteresis — distinct fire and clear
  thresholds — and MUST report flapping rather than firing per crossing.
- **FR-009** Detector evaluation MUST be idempotent and MUST survive a restart
  mid-evaluation without double-firing.
- **FR-010** Concurrent evaluation across replicas MUST use the scheduler's
  existing lease-based claiming.
- **FR-011** A detector that fails to evaluate MUST raise its own failure as an
  attention item, and MUST NOT be silently skipped.
- **FR-012** Detectors MUST be individually enabled, disabled and tested against
  historical signals without firing.

**Incidents**

- **FR-013** An incident MUST carry: subjects (one or more resources), the
  detector or alert that raised it, severity, state, opened and closed times, a
  correlation key, the runs attached to it, the actions taken, and a timeline.
- **FR-014** Incident state MUST be a closed set: open, investigating, awaiting
  human, remediating, resolved, suppressed, and closed-without-action.
- **FR-015** An incident MUST be raised by exactly one lifecycle regardless of
  origin — detector, webhook, or a human opening one by hand.
- **FR-016** Correlation MUST group by the detector's grouping key so one cause
  affecting many resources is one incident with many subjects.
- **FR-017** A recovered condition MUST close its incident after the recovery
  duration, recording self-resolution.
- **FR-018** An incident MUST be closable by a human at any point, with a reason.
- **FR-019** Every state change MUST appear on the incident's timeline with its
  cause and actor.

**Suppression**

- **FR-020** Maintenance windows MUST suppress detectors on the resources they
  cover, and suppression MUST be recorded, never silent.
- **FR-021** A global pause MUST exist that stops all detection without
  unconfiguring anything, and its state MUST be visible everywhere.
- **FR-022** Suppression MUST be scopeable by resource, kind, detector, team and
  time.

**Investigation**

- **FR-023** An opened incident MUST start an investigation whose objective is
  derived from the incident and its subjects, and the run MUST link back.
- **FR-024** Investigation dispatch MUST be rate-limited per team and globally, so
  a hundred simultaneous incidents cannot start a hundred simultaneous runs.
- **FR-025** An incident already under investigation MUST NOT start a second run
  for the same correlation.
- **FR-026** Escalation MUST use the existing escalation registry, and MUST cancel
  when the incident closes.

### Non-functional

- **NFR-001** One evaluation tick over ten thousand resources and one hundred
  detectors MUST complete within a declared budget.
- **NFR-002** Detection MUST add no provider calls beyond what its declared
  pollers make, and MUST respect integration rate limits.
- **NFR-003** The observer MUST be safe to run as more than one replica.
- **NFR-004** Signal storage MUST live in the single datastore and MUST be bounded
  by retention, not by disk.
- **NFR-005** A detector's evaluation MUST be pure with respect to its inputs, so
  it can be replayed against historical signals.

## Success criteria

- **SC-001** A condition crossing and holding opens exactly one incident; a
  condition crossing and recovering inside the duration opens none.
- **SC-002** The same condition firing repeatedly correlates to one incident.
- **SC-003** A recovered condition self-closes its incident after the recovery
  duration.
- **SC-004** A firing inside a maintenance window is suppressed and recorded.
- **SC-005** One cause across fifty resources produces one incident with fifty
  subjects.
- **SC-006** A webhook alert and a detected condition produce structurally
  identical incidents, asserted.
- **SC-007** A failing detector surfaces as an attention item.
- **SC-008** Restart mid-evaluation does not double-fire; two replicas produce one
  outcome.
- **SC-009** A detector replayed against historical signals reproduces exactly
  the firings that happened.
- **SC-010** Ten thousand resources × one hundred detectors evaluate within
  budget.

## Out of scope

- Deciding whether to act on an incident — feature 040.
- Acting and verifying — feature 041.
- Provider-specific detectors — features 047 and 048 ship the homelab set.

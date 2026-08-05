---
name: infrastructure
display_name: Infrastructure investigation
description: Working down the stack from workload to node to network, one layer at a time.
domain: infrastructure
applies_when:
  tags: [kubernetes, cloud, capacity, node, network, scheduling]
use_cases:
  - a workload failing to start, stay up, or receive traffic
  - a symptom that is confined to one zone, node, or cluster
anti_examples:
  - an error inside application code with no infrastructure symptom
---

# Events before logs

The highest-value rule in this domain, and the one most often skipped.

A workload's **events** are the control plane explaining, in its own words, why
it did what it did: why a pod will not schedule, why it was killed, why the
image did not pull. The **logs** are the application talking about something
else entirely, because from inside the container a scheduling failure is
invisible.

Reading logs first on an infrastructure symptom is how an investigation spends
ten minutes inside a process that never started.

## Symptom to first observation

| Symptom | Look at first | Because |
|---|---|---|
| Crash loop | Events, then the previous instance's logs | Events give the exit code and reason; the *previous* logs hold the crash, the current ones hold a process that has not failed yet |
| Killed for memory | Resource limits against actual usage | The limit is usually the thing that changed, not the workload |
| Stuck pending | Events, then node capacity | Nothing schedules it, and the event says which constraint |
| Rollout stuck | Revision history and the new revision's readiness | The new instances are failing a probe; the old ones are fine, which is why traffic looks healthy |
| Running but no traffic | Endpoints and probe results | Readiness failing for a different reason than liveness is the classic, and it reads as an application bug |
| Image will not pull | Events | Registry auth or a tag that does not exist — the event says which |

## Down the stack, one layer at a time

Infrastructure failures look alike from above and are entirely different
underneath. The layers are ordered, so the answer is found by descending rather
than by guessing.

1. **Workload.** Is the expected number of instances running, ready, and
   recently restarted? Restart counts and termination reasons are the highest
   signal-to-noise data in the whole stack.
2. **Scheduling.** If instances are not running, is it because nothing will
   place them? Insufficient capacity, an unsatisfiable constraint, and a taint
   nobody remembers adding all present as "pending".
3. **Node.** If instances run and die, look at where they run. Memory
   pressure, disk pressure, and a node in a not-ready state produce failures
   the application logs describe as inexplicable.
4. **Network.** If instances are healthy and traffic is not arriving, the
   question is routing: service endpoints, load balancer health checks, and
   policy.
5. **Control plane.** Rare, and worth checking once the four above are clean
   rather than first.

## The boundary names the layer

Where a symptom stops is usually more informative than where it appears.

- **One instance:** the instance, or the node under it.
- **One node:** the node — pressure, kernel, disk, or a runtime problem.
- **One zone:** infrastructure, and usually the provider's.
- **Every instance, one workload:** the workload's own configuration or its
  latest release.
- **Every workload, one cluster:** the control plane or a cluster-wide policy.

Establishing the boundary is therefore step one of any infrastructure
investigation, and it costs one grouped query.

## Capacity and saturation

A saturated system fails in ways that point everywhere except at saturation:
latency in unrelated services, timeouts that move around, and errors that
correlate with traffic rather than with any change. When nothing changed and
the symptom tracks load, check the resource that runs out first — connections,
file descriptors, memory, and thread pools before CPU.

Check quotas and limits before concluding that nothing changed. A limit reached
under growing load looks exactly like an unexplained failure, and nothing in
the change history mentions it.

## Before changing anything

Infrastructure remediation is nearly always a write, and the ones that look
harmless are the ones that destroy the evidence. Restarting a workload clears
exactly the state that would have explained why it was unhealthy — the events,
the previous instance's logs, and the memory footprint at the moment it died.

Establish the mechanism first. Then use the remediation tools, which carry
approval and a rollback plan for a reason — not because the action is dangerous
in the abstract, but because the plan is what makes the next thirty seconds
recoverable if it goes wrong.

---
name: cloud_control_plane-kubernetes
display_name: Kubernetes workload investigation
description: Events before logs, and what shipped before either. Events expire in an hour.
domain: cloud_control_plane
applies_when:
  alert_sources: [kubernetes, alertmanager]
  tags: [kubernetes, pod, restart, deploy, oom, crashloop]
directs_tools:
  - kubernetes_workload_events
  - kubernetes_rollout_history
requires:
  integrations: [kubernetes]
---

# Kubernetes workload investigation

Events are the shortest-lived evidence in the cluster and the most explanatory.
The default retention is about an hour, so an investigation that reads logs
first and events second regularly finds the events already gone — and the event
is the line that says `OOMKilled` while the logs say only that the process
stopped.

## Order of operations

1. **Read the events, immediately.** Call `kubernetes_workload_events` for the
   namespace, narrowed to the object the alert named. Do this before anything
   slower, because this is the evidence with a deadline.
2. **Take the reason, not the fact.** `OOMKilled`, `Evicted`,
   `FailedScheduling`, `ImagePullBackOff`, `Unhealthy` — each is a different
   incident with a different fix. "The pod restarted" is the symptom that all
   of them produce.
3. **Ask what shipped.** Call `kubernetes_rollout_history` for the deployment.
   A revision created shortly before the onset is the strongest single lead
   available, and its absence rules out a whole class of cause in one call.
4. **Compare the times yourself.** The tool reports the timeline and does not
   claim causality, because whether four minutes is a coincidence depends on how
   often this team deploys.
5. **Only then reach for logs.** By now you know which container, which window,
   and what to look for. Logs read before this are a search; logs read after it
   are a confirmation.

## Reading the result

An empty event list has two meanings and they are not interchangeable: nothing
happened, or the events expired before anybody asked. Say which one you can
rule out. Concluding "no problems in the namespace" from an empty list an hour
after the incident is the most common wrong answer this integration produces.

## What this is not for

- **Application errors.** Events are the control plane's account of what it did
  to a workload. What the process itself logged is a log question.
- **Fixing anything.** Restarting, scaling, and cordoning are remediations with
  approval gates and rollback plans. Nothing here changes the cluster.
- **Changes that did not go through this deployment** — a config map edit, a
  feature flag, a change to a dependency. The rollout history is silent on all
  of them, and silence there is not evidence that nothing changed.

## Kubernetes specifics

- The alert usually names a pod; the rollout history wants the deployment. The
  pod's name is the deployment's name plus two hashes, so `checkout-7f4c9-x2p1`
  belongs to `checkout`.
- A deployment and its canary share a name prefix and not a selector, so
  revisions are matched by the deployment's own labels. Two workloads with
  similar names do not contaminate each other's history.
- `revisionHistoryLimit` bounds how far back revisions go. Older ones are
  deleted, not hidden.

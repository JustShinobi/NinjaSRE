# Kubernetes

Workload events and rollout history from a cluster's API server. Kubernetes is
the reference integration for the case where NinjaSRE cannot know the egress
allow-list: every deployment's API server is somewhere else, so the operator
declares the hosts and the proxy enforces exactly those.

## Setup

Secret and required status are declared once, in this package's `schema.py`;
this table does not repeat them. It carries what `schema.py` does not show in a
browsable form: what each field is, the minimum permission it needs when it is
secret, and a guide to producing it.

| Field | What it is | Minimum permission | Guide |
|---|---|---|---|
| `endpoint` | The API server address — https://k8s.internal:6443 | — | [Accessing clusters](https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/) |
| `token` | A service account token with the read roles below | get/list on events, deployments.apps and replicasets.apps | [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) |
| `cluster` | A name for the cluster this token authenticates against | — | [Accessing clusters](https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/) |
| `namespace` | The default namespace for namespaced reads | — | [Namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/) |

Sources: all four from the upstream Kubernetes documentation, current as of
this feature.

```bash
ninjasre integrations setup kubernetes
ninjasre integrations verify kubernetes
```

A token rather than a client certificate: a certificate would put a private key
in the same place the token goes, and RBAC is expressed against the service
account either way.

`endpoint` goes to the configuration tree rather than the vault — it is where
the credential proxy reads its egress allow-list from — and it may be left
empty when NinjaSRE runs inside the cluster it watches.

**Running inside the cluster needs no host configuration.** The in-cluster
address `kubernetes.default.svc` is always permitted, because a deployment with
an external endpoint may still run workers inside the cluster and discovering
that at 03:00 is not the moment to find the allow-list one entry short.

Reaching an external endpoint means declaring it at composition:

```python
from integrations.kubernetes.schema import rule_for

rule_for("k8s.acme.example")  # in-cluster is still included
```

## Permissions

The token and the role binding are different objects, created by different
people at different times, and this is the vendor where "the credential works"
and "the credential may do what we need" come apart most often. Connectivity
reads `/version`, which needs authentication and no RBAC beyond it — so a
failure there is the token and never the binding.

| Verb and resource | What it grants | Without it |
|---|---|---|
| `list events` | Read events in the investigated namespaces | `kubernetes_workload_events` cannot run |
| `get deployments.apps` | Read a deployment and its rollout history | `kubernetes_rollout_history` cannot run |
| `list replicasets.apps` | Read the replica sets that are the rollout history | `kubernetes_rollout_history` returns no revisions |

A minimal role:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ninjasre-read
rules:
  - apiGroups: [""]
    resources: ["events", "pods"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list"]
```

Kubernetes can introspect a permission with `SelfSubjectAccessReview`, but that
is itself a create against an API the token may not be allowed to reach — a
probe whose own failure is ambiguous is worse than no probe. So each verb is
checked by performing the read: 200 means permitted, 403 means not, and the
verification output says which was used.

## Limitations

- **Events expire in about an hour** by default. They are the shortest-lived
  evidence in the cluster and the most valuable, which is why the methodology
  reads them first. An empty result may mean nothing happened or may mean the
  events aged out, and those are different findings.
- **Only the retained revisions are visible.** A deployment's
  `revisionHistoryLimit` bounds how far back the rollout history goes;
  older revisions are gone rather than hidden.
- **Everything here is read-only.** Restarting a workload, scaling it, or
  cordoning a node are remediations, and a remediation needs an approval gate
  and a stored rollback plan — they live in the remediation capabilities, not
  one typo away from a read.
- **Namespaced reads need a namespace.** A cluster-wide sweep is not offered:
  every workload's events at once is noise, and the alert already names a
  namespace.
- **Aggregated APIs and custom resources are out of scope.** The four REST
  paths here are the core and apps groups.

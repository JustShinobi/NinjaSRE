# Test infrastructure

Two clusters, one command each way.

| | Local | Cloud-backed |
|---|---|---|
| Create | `make chaos-setup` | `make chaos-setup-eks` |
| Destroy | `make chaos-teardown` | `make chaos-teardown-eks` |

Both create a cluster, install the chaos framework, and wait for it to be ready.
`make e2e-demo-setup` adds the demo application and its observability stack on
top of whichever cluster is current.

**The local cluster is the default and the one to reach for.** It runs every
chaos experiment, costs nothing, and is destroyed by deleting one container. The
cloud-backed cluster exists for the experiments whose behaviour differs on a
managed control plane, and for the cloud end-to-end scenarios that need to be
inside the account they are provisioning into.

## What the scripts assume

Each script checks its own prerequisites and names the missing one rather than
failing part way through. Nothing here reads a credential: the cluster tools
authenticate from the operator's own environment, which is the only arrangement
in which a script that creates cloud infrastructure is not a place a secret
passes through.

## Cleaning up after a run that was killed

A run that was stopped rather than interrupted leaves its fault applied. The
next run's preflight check refuses to start on top of it and says so, and

```bash
make chaos-sweep
```

removes everything carrying this suite's label, whichever run applied it. The
cloud equivalent is `make e2e-reap`, which is also what the scheduled job runs.

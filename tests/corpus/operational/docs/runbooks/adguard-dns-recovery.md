# Recovering AdGuard DNS

When host-adguard.example.invalid stops answering queries.

## Confirm the failure

Resolve a known name against each instance. A timeout on both instances is a
service failure; a timeout on one is a failover that worked.

## Check the memory cgroup before restarting

Read the guest's memory usage and the host's kernel ring buffer for an
out-of-memory kill inside the guest's cgroup. Restarting first destroys this
evidence, and it is the evidence that says whether this is the same failure as
before.

## Restart the resolver

Restart the service on the failing instance. Confirm answers, then confirm the
other instance is still healthy before restarting it.

## Afterwards

Record the query log size at the moment of the stall. The log is held in memory
and is what has previously reached the container's limit.

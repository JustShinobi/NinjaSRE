# AdGuard DNS stalled again — memory cgroup out of memory

The same failure as three days ago, caught early enough to keep the evidence.

## Symptom

AdGuard DNS stopped answering queries on both instances. `dig` against
host-adguard.example.invalid timed out; the web interface still loaded.

## Investigation

Left the container running this time. The kernel ring buffer on the host holds
an out-of-memory kill inside the guest's memory cgroup at the exact minute the
answers stopped. The query log's growth rate matches: the log is held in memory
and the container's limit is 512 MiB.

## Root cause

The memory cgroup limit on the container is reached by the in-memory query log,
the kernel kills the resolver process, and the supervisor restarts it into the
same condition. The service appears to be running throughout, which is why the
first investigation found a healthy container and no reason.

## Correction

Raised the container's memory limit to 1 GiB and capped the query log's
retention so it cannot grow without bound. Added a memory-pressure detector on
the guest.

## Recurrence of

2026-07-17-adguard-dns-stall-both-instances

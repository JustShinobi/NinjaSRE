# AdGuard DNS stalled on both instances

Both resolvers stopped answering within four minutes of each other. Every
workload that resolves through them reported name resolution failures.

## Symptom

AdGuard DNS stopped answering queries on both instances. `dig` against
host-adguard.example.invalid timed out; the web interface still loaded.

## Investigation

Checked the container state on both guests — running, no restarts. Checked the
upstream resolvers — answering directly. Checked the query log — it stops at
09:41 on the primary and 09:45 on the secondary, with no error line. Restarting
the service restored answers immediately, which ended the outage and also ended
the evidence.

## Root cause

Not established. The service stopped processing without logging a reason and
the restart destroyed the state that would have said why. Recorded so the next
occurrence is not investigated from zero.

## Correction

Restarted AdGuard on both instances. Added a synthetic resolution check so the
next stall is detected rather than reported by a user.

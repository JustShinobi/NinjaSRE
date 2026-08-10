# A backup job was disabled and nobody noticed for eleven weeks

The job existed, was listed, and had been switched off.

## Symptom

A restore request could not be satisfied. The most recent backup for the guest
was eleven weeks old.

## Investigation

The job is present in the schedule listing and reads `enabled: false`. It was
disabled during a datastore migration and never re-enabled. Nothing alerts on a
job that is not running, because the alerting was on job failure.

## Root cause

Alerting on failure cannot see a job that never runs. A disabled job produces no
failures.

## Correction

Re-enabled the job. Added a detector on backup age rather than on backup
failure, so absence is what is watched.

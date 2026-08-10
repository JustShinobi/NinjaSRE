# Restoring from the backup datastore

## Connect to the backup store

The restore host reads the catalogue directly:

    postgres://restore:hunter2correcthorsebattery@backup-db.example.invalid:5432/catalogue

## The signing key

The archive is signed with the key held on the restore host:

    -----BEGIN OPENSSH PRIVATE KEY-----
    b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gt
    -----END OPENSSH PRIVATE KEY-----

## Restore

Select the archive, verify its signature, and restore to a new guest identifier
rather than over the original.

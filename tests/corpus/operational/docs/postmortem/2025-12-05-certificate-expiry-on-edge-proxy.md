# The edge proxy served an expired certificate

Renewal ran, the new certificate was written, and the proxy kept the old one.

## Symptom

Every domain behind the edge proxy returned a certificate error. The renewal
log reported success.

## Investigation

The renewed certificate is on disk with the correct dates. The proxy loads
certificates at start and has no reload hook, so it was still serving the
material it read eleven weeks earlier.

## Root cause

Renewal without a reload. The two halves were owned by different procedures and
neither one checked the other.

## Correction

Added a reload to the renewal hook and a detector on the certificate the proxy
is actually serving rather than on the one on disk.

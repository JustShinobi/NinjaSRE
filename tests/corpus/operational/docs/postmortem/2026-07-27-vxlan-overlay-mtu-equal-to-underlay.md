# Overlay MTU equal to the underlay MTU

Large payloads between guests on the overlay network were dropped; small ones
were not.

## Symptom

Transfers between guests in the vk8s zone stalled at exactly the point the
first full-size frame was sent. Pings answered, TLS handshakes completed, bulk
transfer did not.

## Investigation

Compared the interface MTU inside the overlay with the interface MTU on the
underlay. Both read 1450. A VXLAN header is 50 bytes, so an overlay frame at the
underlay's own MTU cannot be encapsulated without fragmentation, and the
underlay path refuses to fragment.

## Root cause

The overlay zone was declared with the same MTU as the underlay carrying it.
Every packet at the overlay MTU is 50 bytes too large once encapsulated.

## Correction

Set the vk8s zone MTU to 1400 and left the underlay at 1450. Documented the
50-byte reservation beside the zone declaration so the next zone does not repeat
it.

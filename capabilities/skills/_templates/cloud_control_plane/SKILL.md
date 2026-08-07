---
name: cloud_control_plane-VENDOR
display_name: VENDOR cloud investigation
description: Cloud resource state and recent changes, read from the control plane.
domain: cloud_control_plane
applies_when:
  alert_sources: [VENDOR]
  tags: [cloud, infrastructure, capacity, configuration]
directs_tools:
  - VENDOR_describe_resource
  - VENDOR_list_recent_changes
requires:
  integrations: [VENDOR]
---

# VENDOR cloud investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Establish the resource's current state**, and whether it matches what
   is declared.
2. **Read recent changes against the symptom's onset**, not against the
   alert time.
3. **Check the boundary.** One resource, one zone, or one account — where a
   symptom stops usually names the layer.
4. **Check quotas and limits** before concluding that nothing changed. A
   limit reached under growing load looks like an unexplained failure.

## What this is not for

- Application behaviour inside a healthy resource.
- Making changes: remediation tools carry approval and rollback for that.

## Notes for this vendor

- The eventual-consistency window on this vendor's read APIs.
- Which changes appear in the audit trail and which do not.

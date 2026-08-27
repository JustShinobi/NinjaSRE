-- Fifty rows is an evening's worth, and small enough to read. Both decisions
-- are in here, and finding them is the reader's job rather than a filter's.
SELECT occurred_at,
       actor_kind,
       actor_id,
       action,
       resource_kind,
       resource_id,
       outcome
FROM audit_events
WHERE org_id = :org
  AND resource_kind IN (:approval_audit_kind, :remediation_audit_kind)
ORDER BY occurred_at DESC
LIMIT 50;

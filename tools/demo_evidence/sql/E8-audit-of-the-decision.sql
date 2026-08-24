SELECT occurred_at,
       actor_kind,
       actor_id,
       action,
       resource_kind,
       resource_id,
       outcome
FROM audit_events
WHERE org_id = :org
  AND resource_id = :approval
  AND resource_kind IN (:approval_audit_kind, :remediation_audit_kind)
ORDER BY occurred_at;

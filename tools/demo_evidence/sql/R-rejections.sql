SELECT approval_id,
       action,
       state,
       decided_by,
       decided_at,
       reason
FROM approvals
WHERE org_id = :org
  AND state = :rejected_state
ORDER BY decided_at DESC;

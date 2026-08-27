SELECT approval_id,
       state,
       decided_by,
       decided_at,
       reason,
       requested_at,
       expires_at
FROM approvals
WHERE org_id = :org
  AND approval_id = :approval;

SELECT approval_id,
       action,
       side_effect_level,
       state,
       requested_at,
       expires_at,
       arguments ->> 'change_type' AS change_type
FROM approvals
WHERE org_id = :org
  AND run_id = :run
ORDER BY requested_at;

SELECT plan_id,
       created_at,
       notes,
       steps
FROM rollback_plans
WHERE org_id = :org
  AND approval_id = :approval;

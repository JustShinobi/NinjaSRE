-- A named failure is an outcome and closes the loop negatively. What does not
-- close the loop is no row at all.
SELECT action_id,
       capability,
       resource_id,
       run_id,
       incident_id,
       state,
       verdict,
       rollback,
       autonomous,
       executed_at,
       due_at,
       verified_at,
       left(detail, 200) AS detail
FROM remediation_outcomes
WHERE org_id = :org
  AND resource_id = :resource
ORDER BY executed_at DESC;

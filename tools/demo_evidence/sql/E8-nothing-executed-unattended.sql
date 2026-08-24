-- This must read nought at the end. A row here is an action carried out with
-- no human decision recorded against it.
SELECT count(*) AS unattended_executions
FROM remediation_outcomes
WHERE org_id = :org
  AND autonomous IS TRUE;

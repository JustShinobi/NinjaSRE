-- Nought here does not mean the screen is broken. It means no write was ever
-- proposed, and the process log says on which of its pieces that turned.
SELECT count(*) AS remediation_proposals
FROM approvals
WHERE org_id = :org
  AND arguments ->> 'change_type' = :remediation_change_type;

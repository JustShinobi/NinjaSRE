SELECT count(*) AS evidence_rows
FROM evidence
WHERE org_id = :org
  AND run_id = :run;

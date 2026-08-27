-- The proof is that the first column does not open with markdown syntax while
-- the second still does. One sentence, one document, two fields.
SELECT headline,
       left(summary, 120) AS summary_opens_with,
       status,
       finished_at
FROM agent_runs
WHERE org_id = :org
  AND run_id = :run;

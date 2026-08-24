SELECT count(*) AS run_turns
FROM run_turns
WHERE org_id = :org
  AND run_id = :run;

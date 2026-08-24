SELECT count(*) AS tool_calls
FROM tool_calls
WHERE org_id = :org
  AND run_id = :run;

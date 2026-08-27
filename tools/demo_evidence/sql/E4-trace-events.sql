SELECT count(*) AS trace_events
FROM trace_events
WHERE org_id = :org
  AND run_id = :run;

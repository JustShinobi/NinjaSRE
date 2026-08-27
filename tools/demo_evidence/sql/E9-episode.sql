SELECT episode_id,
       title,
       outcome,
       occurred_at,
       components
FROM episodes
WHERE org_id = :org
  AND run_id = :run;

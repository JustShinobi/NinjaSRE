-- An unpriced turn carries an empty usage document rather than a zero.
-- The difference is the whole point of reading this turn by turn.
SELECT "index",
       started_at,
       finished_at,
       usage
FROM run_turns
WHERE org_id = :org
  AND run_id = :run
ORDER BY "index";

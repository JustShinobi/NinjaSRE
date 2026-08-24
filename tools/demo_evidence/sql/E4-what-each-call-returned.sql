-- Ordered by the sequence the recorder assigned, not by time. Two calls in one
-- concurrent batch routinely share a microsecond.
SELECT recorded_seq,
       tool_name,
       status,
       started_at,
       finished_at,
       error
FROM tool_calls
WHERE org_id = :org
  AND run_id = :run
ORDER BY recorded_seq;

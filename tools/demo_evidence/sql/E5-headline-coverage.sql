-- How many runs carry a sentence of their own, and how many were written before
-- the column existed. A run backfilled with an empty sentence is the one case
-- where the read path has to synthesise a name, and it is the likeliest reason
-- for a screen rule to hold against a fixture and fail against real history.
SELECT count(*) AS runs,
       count(*) FILTER (WHERE headline = '') AS without_a_sentence,
       count(*) FILTER (WHERE summary LIKE '#%') AS document_opens_with_syntax,
       min(started_at) AS oldest,
       max(started_at) AS newest
FROM agent_runs
WHERE org_id = :org;

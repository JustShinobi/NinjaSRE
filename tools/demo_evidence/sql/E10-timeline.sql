-- The incident is found by either spelling of its address, because what an
-- operator has in hand is whatever the console put in the URL.
SELECT kind,
       at,
       actor,
       cause,
       left(detail, 160) AS detail
FROM incident_timeline
WHERE org_id = :org
  AND incident_id = (
        SELECT incident_id
        FROM incidents
        WHERE org_id = :org
          AND (incident_id = :incident OR public_id = :incident)
      )
ORDER BY at;

SELECT public_id,
       title,
       state,
       severity,
       origin,
       origin_id,
       opened_at,
       closed_at,
       subjects,
       run_ids,
       actions
FROM incidents
WHERE org_id = :org
  AND (incident_id = :incident OR public_id = :incident);

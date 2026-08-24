SELECT title,
       state,
       severity,
       subjects,
       run_ids,
       actions,
       closed_at,
       close_reason,
       self_resolved
FROM incidents
WHERE org_id = :org
  AND (incident_id = :incident OR public_id = :incident);

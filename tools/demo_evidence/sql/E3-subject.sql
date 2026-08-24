SELECT resource_id,
       kind,
       source,
       native_id,
       display_name,
       health,
       last_seen_at,
       absent_since
FROM estate_resources
WHERE org_id = :org
  AND resource_id = :resource;

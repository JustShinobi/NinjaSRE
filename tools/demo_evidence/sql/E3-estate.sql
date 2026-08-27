SELECT count(*) AS present_resources
FROM estate_resources
WHERE org_id = :org
  AND absent_since IS NULL;

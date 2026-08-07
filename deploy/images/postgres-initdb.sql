-- Installs the two extensions ADR 0004 depends on, once, at cluster init.
--
-- Into template1 as well as the default database, so a deployment that later
-- creates a second database — a scratch target for a restore verification, say
-- — gets one that already has them rather than one that quietly does not.
--
-- The platform verifies availability at startup rather than trusting this file.
-- An operator running their own managed PostgreSQL never executed it, and a
-- deployment that assumed otherwise would fail inside a query instead of at
-- boot with something actionable.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

\connect template1

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

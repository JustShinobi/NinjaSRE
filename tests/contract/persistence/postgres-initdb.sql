-- Installs the two extensions ADR 0004 depends on, once, at cluster init.
--
-- Into template1 as well as the default database: the contract suite creates a
-- database per run so that a failed run cannot leave state behind for the next
-- one, and a template without the extensions would mean every one of those
-- databases starting without them.
--
-- The platform verifies availability at startup rather than trusting this file
-- (FR-002). A deployment that provisioned its own PostgreSQL never ran it.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

\connect template1

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

# The reference datastore, as the contract suite needs it: PostgreSQL 16 with
# both extensions ADR 0004 depends on.
#
# No published image carries both, so this one adds pgvector to the Apache
# Software Foundation's AGE image. That direction round is deliberate — AGE is
# a compiled extension with a PostgreSQL-version-specific build, while pgvector
# ships as a PGDG package the base image's apt sources already point at.
#
# Versions are pinned. A test fixture that silently follows `latest` is a suite
# that fails one morning for a reason nobody changed.
FROM apache/age:release_PG16_1.6.0

# 0.8.6 is what PGDG trixie carries for PostgreSQL 16. The pin is the point;
# HNSW behaviour is what SC-002 measures, and it is a property of a version.
ARG PGVECTOR_PACKAGE=postgresql-16-pgvector=0.8.6-1.pgdg13+1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes "${PGVECTOR_PACKAGE}" \
    && rm -rf /var/lib/apt/lists/*

# Created before the server accepts a connection, so a test never races the
# bootstrap. `docker-entrypoint-initdb.d` runs once, against the template the
# default database is created from, which is why the extensions exist in every
# database the suite makes rather than only in the first.
#
# AGE additionally needs its search path set and its graph created, but that is
# schema rather than installation, and it belongs in the platform's own
# bootstrap where a deployment without this Dockerfile also gets it.
COPY postgres-initdb.sql /docker-entrypoint-initdb.d/10-extensions.sql

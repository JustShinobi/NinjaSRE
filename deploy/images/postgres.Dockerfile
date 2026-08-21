# The one datastore: PostgreSQL with both extensions ADR 0004 depends on.
#
# No published image carries pgvector and Apache AGE together, so this adds
# pgvector to the Apache Software Foundation's AGE image. That direction round
# is deliberate — AGE is a compiled extension built against a specific
# PostgreSQL major version, while pgvector ships as a PGDG package the base
# image's apt sources already point at. Doing it the other way would mean
# compiling AGE.
#
# Both versions are pinned, and the pin is the point. HNSW recall is a property
# of a pgvector version, and a datastore that silently followed `latest` is one
# that changes retrieval quality on a morning nobody touched anything.

# syntax=docker/dockerfile:1
ARG BASE_POSTGRES=apache/age:release_PG16_1.6.0

FROM ${BASE_POSTGRES}

LABEL org.opencontainers.image.title="NinjaSRE PostgreSQL" \
      org.opencontainers.image.description="PostgreSQL with pgvector and Apache AGE"

# What PGDG carries for PostgreSQL 16 on this base.
ARG PGVECTOR_PACKAGE=postgresql-16-pgvector=0.8.6-1.pgdg13+1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes "${PGVECTOR_PACKAGE}" \
    && rm -rf /var/lib/apt/lists/*

# Runs once, against the template the default database is created from, so the
# extensions exist in every database this server makes rather than only in the
# first. Creating them here means the application never races the bootstrap.
COPY deploy/images/postgres-initdb.sql /docker-entrypoint-initdb.d/10-extensions.sql

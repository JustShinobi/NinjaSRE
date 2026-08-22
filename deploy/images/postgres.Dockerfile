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

# Security updates for what the base carries, named one by one rather than a
# blanket `apt-get upgrade`. Apache AGE is a compiled extension built against
# this image's PostgreSQL, and an upgrade that moved the server out from under
# it would break the graph in a way that only shows up at a query — the same
# coupling that makes the base pinned in the first place. None of the packages
# below is the server: they are the TLS, Kerberos, GnuPG and util-linux
# libraries around it, and every one of them was reported with a fix available.
#
# Not pinned to a version, deliberately and unlike everything else here. Pinning
# a security update breaks the build on the day the next one is published, which
# is the day you want it picked up.
RUN apt-get update \
    && apt-get install --no-install-recommends --only-upgrade --yes \
        bsdutils dirmngr gnupg gnupg-l10n gpg gpg-agent gpgconf gpgsm \
        libblkid1 libcap2 libgnutls30t64 libgssapi-krb5-2 libk5crypto3 \
        libkrb5-3 libkrb5support0 liblastlog2-2 libmount1 libpq5 \
        libsmartcols1 libssl3t64 libuuid1 login mount openssl \
        openssl-provider-legacy util-linux \
    && apt-get install --no-install-recommends --yes gosu \
    # The vendored `gosu` at /usr/local/bin is a Go binary, and the Go standard
    # library compiled into it is where this image's CRITICAL findings live —
    # somewhere `apt` cannot reach. Debian builds its own against the
    # distribution's Go, so the entrypoint keeps the command it calls and stops
    # carrying a 2024 runtime to do it.
    && ln -sf /usr/sbin/gosu /usr/local/bin/gosu \
    && rm -rf /var/lib/apt/lists/*

# Runs once, against the template the default database is created from, so the
# extensions exist in every database this server makes rather than only in the
# first. Creating them here means the application never races the bootstrap.
COPY deploy/images/postgres-initdb.sql /docker-entrypoint-initdb.d/10-extensions.sql

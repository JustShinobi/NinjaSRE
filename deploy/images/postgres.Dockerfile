# The one datastore: PostgreSQL with both extensions ADR 0004 depends on.
#
# No published image carries pgvector and Apache AGE together, and for a long
# time this file solved that by starting from Apache's own AGE image and adding
# pgvector on top. That worked, and it quietly handed the deployment's most
# important version decision to somebody else's image release cadence: the graph
# extension's image is published per PostgreSQL major, so the newest major this
# deployment could run was the newest major Apache had built an image for. That
# is how a project ends up two majors behind on its own datastore.
#
# So the direction is reversed. This starts from the official PostgreSQL image —
# which is what pins the major, where the major decision belongs — and compiles
# the graph extension into it from the upstream's published release artefact.
# pgvector stays a PGDG package, because it is one for every major.
#
# The artefact is verified before it is compiled. What comes out of that build is
# a shared library the database server loads into its own process, so "the
# download succeeded" is not a sufficient reason to trust it.
#
# Both versions are pinned, and the pin is the point. HNSW recall is a property
# of a pgvector version, and a datastore that silently followed `latest` is one
# that changes retrieval quality on a morning nobody touched anything.
#
# The same artefact, the same checksum and the same pgvector version are used by
# `deploy/proxmox/guest/install-system.sh`, so a deployment installed natively
# and one installed from these images hold their data the same way and their
# dumps are interchangeable.

# syntax=docker/dockerfile:1
ARG BASE_POSTGRES=postgres:18.4-trixie

# --- Build the graph extension -------------------------------------------------
#
# In a stage of its own, from the same base, so the runtime image inherits the
# compiled library and nothing that could compile another one.

FROM ${BASE_POSTGRES} AS build

ARG PG_MAJOR_VERSION=18

# The upstream publishes one release artefact per PostgreSQL major, so this URL
# and the major above are one decision in two places.
ARG AGE_SOURCE_URL=https://github.com/apache/age/releases/download/PG18%2Fv1.8.0-rc0/apache-age-1.8.0-src.tar.gz
ARG AGE_SOURCE_SHA256=555736a31974255223778959ca8bcd9cb710b93a8fab1d846eaf3e84704b9417

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        build-essential \
        flex \
        bison \
        perl \
        curl \
        ca-certificates \
        "postgresql-server-dev-${PG_MAJOR_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Verified first, built second. A checksum that is checked after the compiler
# has already run is a checksum that documents an incident.
RUN curl -fsSL --retry 5 --retry-delay 2 --retry-connrefused "${AGE_SOURCE_URL}" -o age-src.tar.gz \
    && printf '%s  age-src.tar.gz\n' "${AGE_SOURCE_SHA256}" | sha256sum -c - \
    && tar --extract --gzip --file age-src.tar.gz --strip-components=1 \
    && rm age-src.tar.gz

# ``DESTDIR`` so the whole install lands under one directory the runtime stage
# can copy, rather than being scattered through this stage's filesystem.
RUN make PG_CONFIG="/usr/lib/postgresql/${PG_MAJOR_VERSION}/bin/pg_config" \
    && make PG_CONFIG="/usr/lib/postgresql/${PG_MAJOR_VERSION}/bin/pg_config" \
        DESTDIR=/out install

# --- The server -----------------------------------------------------------------

FROM ${BASE_POSTGRES} AS runtime

LABEL org.opencontainers.image.title="NinjaSRE PostgreSQL" \
      org.opencontainers.image.description="PostgreSQL with pgvector and Apache AGE"

ARG PG_MAJOR_VERSION=18

# What PGDG carries for this major on this base.
ARG PGVECTOR_PACKAGE=postgresql-18-pgvector=0.8.6-1.pgdg13+1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes "${PGVECTOR_PACKAGE}" \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /out/usr/lib/postgresql/${PG_MAJOR_VERSION}/lib/ \
    /usr/lib/postgresql/${PG_MAJOR_VERSION}/lib/
COPY --from=build /out/usr/share/postgresql/${PG_MAJOR_VERSION}/extension/ \
    /usr/share/postgresql/${PG_MAJOR_VERSION}/extension/

# Runs once, against the template the default database is created from, so the
# extensions exist in every database this server makes rather than only in the
# first. Creating them here means the application never races the bootstrap.
COPY deploy/images/postgres-initdb.sql /docker-entrypoint-initdb.d/10-extensions.sql

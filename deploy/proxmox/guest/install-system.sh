#!/bin/sh
#
# Install everything NinjaSRE needs directly into the LXC guest: PostgreSQL 18
# with both extensions, and the exact CPython the project targets.
# No container runtime, no images — the processes run under the guest's own init.
#
# Runs in the guest. `/bin/sh` and no bashisms, because one of the two supported
# templates is Alpine and its shell is busybox ash.
#
# This is the only file that knows a package manager, and it is where the two
# distributions actually differ. Everything downstream talks to `pg_config`, a
# virtual environment and an init system, and cannot tell which it got.
#
# The one thing neither distribution packages is the graph extension. It is
# compiled here, from a checksummed release artefact, against this exact
# PostgreSQL major version — which is also why the major is pinned rather than
# "whatever the distribution ships": the extension is built against one and
# loads into no other.

set -eu

DISTRO=""
PG_MAJOR="18"

# The graph extension: the published release artefact, not a clone of a branch.
# A branch moves, and what gets compiled into a database server should not. The
# checksum is the point of the tarball — without it this step trusts whatever
# the network returned.
#
# The upstream publishes one artefact per PostgreSQL major, so the major above
# and this URL are one decision in two places.
AGE_VERSION="1.8.0"
AGE_SOURCE_URL="https://github.com/apache/age/releases/download/PG18%2Fv1.8.0-rc0/apache-age-1.8.0-src.tar.gz"
AGE_SOURCE_SHA256="555736a31974255223778959ca8bcd9cb710b93a8fab1d846eaf3e84704b9417"

# The vector extension, for the distribution whose package is built against a
# different major. Pinned to the same version the other distribution's package
# carries: recall is a property of a pgvector version, so two deployments on two
# versions is two answers to the same search.
PGVECTOR_REPOSITORY="https://github.com/pgvector/pgvector.git"
PGVECTOR_REF="v0.8.6"

# The interpreter the platform runs on, and it is the same one in every
# deployment mode. Neither distribution packages it — Alpine 3.23 ships 3.12 and
# Debian 13 ships 3.13 — so taking the distribution's Python would mean the
# container images and the native install ran different interpreters, and a bug
# that only appears on one of them is a bug nobody reproduces.
#
# `uv` fetches a standalone build (and verifies it), which works the same on
# glibc and on musl. That is the whole reason it is here rather than a
# `apt install python3`.
PYTHON_VERSION="3.14.7"

# Pinned and checksummed, because it is the thing that fetches the interpreter.
UV_VERSION="0.12.3"
UV_SHA256_X86_64_GNU="600cf9a742aca00d292673b16b5acffaa7b8c269a364ad0c2e79498dcb1fe101"
UV_SHA256_X86_64_MUSL="0643b9fb8c9fb27458e709ce6ff939695013c41975ff7b02d3f3b138d8d4bdb3"
UV_SHA256_AARCH64_GNU="bb66cb52e7b1823aed1183630d8d8e5c958840d584a4c55ec10a4cfc168dcca2"
UV_SHA256_AARCH64_MUSL="fa513fca1eb2913334c944fe9adbdd410274a1cbe8dd05d03699a9eb85311d4e"

SERVICE_USER="ninjasre"
STATE_DIR="/var/lib/ninjasre"

while [ $# -gt 0 ]; do
    case "$1" in
        --distro) DISTRO="$2"; shift 2 ;;
        --pg-major) PG_MAJOR="$2"; shift 2 ;;
        --age-url) AGE_SOURCE_URL="$2"; shift 2 ;;
        --age-sha256) AGE_SOURCE_SHA256="$2"; shift 2 ;;
        --python-version) PYTHON_VERSION="$2"; shift 2 ;;
        *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done

log() { printf '    [guest] %s\n' "$*"; }
die() { printf '    [guest] fail: %s\n' "$*" >&2; exit 1; }

detected="$(. /etc/os-release && printf '%s' "${ID}")"
if [ -z "${DISTRO}" ]; then
    DISTRO="${detected}"
elif [ "${DISTRO}" != "${detected}" ]; then
    die "asked for ${DISTRO} but this guest is ${detected}"
fi

# --- Packages, PostgreSQL and the vector extension ---------------------------

case "${DISTRO}" in
    debian)
        export DEBIAN_FRONTEND=noninteractive
        # A fresh template has generated no locales, so every package that runs
        # perl warns about it. Nothing here needs one.
        export LC_ALL=C LANG=C

        log "installing base packages"
        apt-get update -qq
        apt-get install -y -qq --no-install-recommends \
            ca-certificates curl gnupg git build-essential flex bison perl \
            libpq-dev openssl xz-utils >/dev/null

        # PostgreSQL from the project's own repository, not the distribution's.
        # Debian 13 ships 17 and the graph extension here is built for 18;
        # taking the distribution's version would mean one that cannot load.
        log "adding the PostgreSQL project's repository"
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
            -o /etc/apt/keyrings/pgdg.asc
        chmod a+r /etc/apt/keyrings/pgdg.asc

        codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME}")"
        if ! curl -fsI "https://apt.postgresql.org/pub/repos/apt/dists/${codename}-pgdg/Release" >/dev/null 2>&1; then
            log "no upstream packages for '${codename}' yet, falling back to bookworm"
            codename="bookworm"
        fi
        printf 'deb [signed-by=/etc/apt/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
            "${codename}" >/etc/apt/sources.list.d/pgdg.list

        log "installing PostgreSQL ${PG_MAJOR} and the vector extension"
        apt-get update -qq
        apt-get install -y -qq --no-install-recommends \
            "postgresql-${PG_MAJOR}" \
            "postgresql-${PG_MAJOR}-pgvector" \
            "postgresql-server-dev-${PG_MAJOR}" >/dev/null

        PG_CONFIG="/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config"
        PG_SERVICE="postgresql@${PG_MAJOR}-main"
        ;;

    alpine)
        log "installing base packages"
        if ! grep -q '^[^#].*/community' /etc/apk/repositories; then
            sed -i '/\/community/s/^#//' /etc/apk/repositories
        fi
        apk update --quiet
        # `perl` is not optional: the graph extension generates its keyword list
        # with a perl script, and its absence fails the build two minutes in
        # with a message that names only the Makefile line.
        apk add --quiet --no-cache \
            ca-certificates curl git build-base flex bison perl \
            openssl libffi-dev openssl-dev xz \
            "postgresql${PG_MAJOR}" "postgresql${PG_MAJOR}-contrib" "postgresql${PG_MAJOR}-dev"

        PG_CONFIG="/usr/libexec/postgresql${PG_MAJOR}/pg_config"
        PG_SERVICE="postgresql"

        # Alpine does package the vector extension against this major, but at
        # a different version from the one the other distribution's repository
        # carries. Built from source so both distributions run the same one:
        # recall is a property of a pgvector version, and a deployment whose
        # search results depend on which guest it was installed in is worse
        # than one that spends twenty seconds compiling.
        log "building the vector extension ${PGVECTOR_REF}"
        rm -rf /tmp/pgvector
        git clone -q --depth 1 --branch "${PGVECTOR_REF}" "${PGVECTOR_REPOSITORY}" /tmp/pgvector
        make -C /tmp/pgvector PG_CONFIG="${PG_CONFIG}" >/tmp/pgvector-build.log 2>&1 \
            || { tail -20 /tmp/pgvector-build.log >&2; die "the vector extension did not build"; }
        make -C /tmp/pgvector PG_CONFIG="${PG_CONFIG}" install >>/tmp/pgvector-build.log 2>&1 \
            || die "the vector extension did not install"
        rm -rf /tmp/pgvector
        ;;

    *)
        die "unsupported distribution '${DISTRO}' — this flow installs on debian and alpine"
        ;;
esac

[ -x "${PG_CONFIG}" ] || die "no pg_config at ${PG_CONFIG} after installing PostgreSQL ${PG_MAJOR}"
log "PostgreSQL $("${PG_CONFIG}" --version | awk '{print $2}')"

# --- The graph extension -----------------------------------------------------
#
# Neither distribution packages it, so both compile it. It is a PostgreSQL
# extension in C built against one major version's server headers, which is why
# this runs after the server is installed and uses that server's own pg_config
# rather than whichever one is first on PATH.

if [ -f "$("${PG_CONFIG}" --sharedir)/extension/age.control" ]; then
    log "the graph extension is already installed"
else
    log "fetching the graph extension ${AGE_VERSION}"
    rm -rf /tmp/age
    mkdir -p /tmp/age
    curl -fsSL "${AGE_SOURCE_URL}" -o /tmp/age/source.tar.gz \
        || die "could not fetch the graph extension from ${AGE_SOURCE_URL}"

    # Verified before anything is compiled, because what is being built here is
    # a shared library the database server will load into its own process.
    printf '%s  /tmp/age/source.tar.gz\n' "${AGE_SOURCE_SHA256}" | sha256sum -c - >/dev/null 2>&1 \
        || die "the graph extension's checksum does not match — refusing to build it"
    log "checksum verified"

    tar -xzf /tmp/age/source.tar.gz -C /tmp/age
    source_dir="$(find /tmp/age -maxdepth 1 -mindepth 1 -type d | head -1)"
    [ -n "${source_dir}" ] || die "the graph extension's archive had no source directory"

    log "building the graph extension (a few minutes)"
    make -C "${source_dir}" PG_CONFIG="${PG_CONFIG}" >/tmp/age-build.log 2>&1 \
        || { tail -25 /tmp/age-build.log >&2; die "the graph extension did not build"; }
    make -C "${source_dir}" PG_CONFIG="${PG_CONFIG}" install >>/tmp/age-build.log 2>&1 \
        || die "the graph extension did not install"
    rm -rf /tmp/age
fi

# --- The cluster -------------------------------------------------------------
#
# Debian's packaging creates and starts a cluster during installation. Alpine's
# does not, on the principle that where the data lives is the administrator's
# decision — so it is made here, once, and only if there is no cluster already.

case "${DISTRO}" in
    debian)
        systemctl enable --now "${PG_SERVICE}" >/dev/null 2>&1 || true
        ;;
    alpine)
        data_dir="/var/lib/postgresql/${PG_MAJOR}/data"
        if [ ! -f "${data_dir}/PG_VERSION" ]; then
            log "initialising the cluster at ${data_dir}"
            install -d -o postgres -g postgres -m 0700 "${data_dir}"
            cat >/etc/conf.d/postgresql <<EOF
# Written by NinjaSRE provisioning.
data_dir="${data_dir}"
initdb_opts="--encoding=UTF8 --locale=C"
EOF
            su postgres -c "${PG_CONFIG%/pg_config}/initdb --pgdata='${data_dir}' --encoding=UTF8 --locale=C" >/dev/null
        fi
        rc-update add "${PG_SERVICE}" default >/dev/null
        rc-service "${PG_SERVICE}" start >/dev/null 2>&1 || rc-service "${PG_SERVICE}" restart >/dev/null
        ;;
esac

attempt=0
while [ "${attempt}" -lt 60 ]; do
    if su postgres -c "psql -c 'SELECT 1' postgres" >/dev/null 2>&1; then
        break
    fi
    attempt=$((attempt + 1))
    sleep 1
done
[ "${attempt}" -lt 60 ] || die "PostgreSQL did not accept a connection within 60s"
log "PostgreSQL is accepting connections"

# --- The interpreter ------------------------------------------------------------
#
# Fetched rather than taken from the distribution, so every deployment mode runs
# the same one. `uv` is verified against a recorded checksum before it is used,
# and it verifies the interpreter it downloads in turn.

UV="/usr/local/bin/uv"

if [ ! -x "${UV}" ]; then
    architecture="$(uname -m)"
    case "${DISTRO}:${architecture}" in
        alpine:x86_64)  uv_target="x86_64-unknown-linux-musl";  uv_sha="${UV_SHA256_X86_64_MUSL}" ;;
        alpine:aarch64) uv_target="aarch64-unknown-linux-musl"; uv_sha="${UV_SHA256_AARCH64_MUSL}" ;;
        *:x86_64)       uv_target="x86_64-unknown-linux-gnu";   uv_sha="${UV_SHA256_X86_64_GNU}" ;;
        *:aarch64)      uv_target="aarch64-unknown-linux-gnu";  uv_sha="${UV_SHA256_AARCH64_GNU}" ;;
        *) die "no pinned uv build for ${DISTRO} on ${architecture}" ;;
    esac

    log "fetching uv ${UV_VERSION} (${uv_target})"
    rm -rf /tmp/uv-install
    mkdir -p /tmp/uv-install
    curl -fsSL --retry 5 --retry-delay 2 --retry-connrefused \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${uv_target}.tar.gz" \
        -o /tmp/uv-install/uv.tar.gz \
        || die "could not fetch uv ${UV_VERSION}"

    printf '%s  /tmp/uv-install/uv.tar.gz\n' "${uv_sha}" | sha256sum -c - >/dev/null 2>&1 \
        || die "uv's checksum does not match — refusing to run it"

    tar -xzf /tmp/uv-install/uv.tar.gz -C /tmp/uv-install
    install -m 0755 "/tmp/uv-install/uv-${uv_target}/uv" "${UV}"
    rm -rf /tmp/uv-install
fi
log "uv $("${UV}" --version | awk '{print $2}')"

# Into a fixed directory rather than root's home, because the service account
# has to read it and a home directory is not where a shared runtime belongs.
UV_PYTHON_INSTALL_DIR="/opt/ninjasre/python"
export UV_PYTHON_INSTALL_DIR
install -d -m 0755 /opt/ninjasre "${UV_PYTHON_INSTALL_DIR}"

log "installing CPython ${PYTHON_VERSION}"
"${UV}" python install "${PYTHON_VERSION}" >/tmp/uv-python.log 2>&1 \
    || { tail -15 /tmp/uv-python.log >&2; die "CPython ${PYTHON_VERSION} did not install"; }

PYTHON="$("${UV}" python find "${PYTHON_VERSION}")"
[ -x "${PYTHON}" ] || die "uv reported no interpreter at ${PYTHON}"

# Recorded where the second half of the flow can find it without guessing, and
# where an operator debugging the guest can read it.
printf '%s\n' "${PYTHON}" >/opt/ninjasre/python-path
chmod 0644 /opt/ninjasre/python-path
log "Python $("${PYTHON}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

# --- The account the platform runs as ----------------------------------------
#
# A system account with no login shell and no home of its own. The state
# directory is its only writable path, which is what makes the service units'
# filesystem hardening a statement rather than a hope.

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    log "creating the ${SERVICE_USER} account"
    case "${DISTRO}" in
        debian)
            adduser --system --group --no-create-home \
                --home "${STATE_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}" >/dev/null
            ;;
        alpine)
            addgroup -S "${SERVICE_USER}"
            adduser -S -D -H -h "${STATE_DIR}" -s /sbin/nologin -G "${SERVICE_USER}" "${SERVICE_USER}"
            ;;
    esac
fi

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${STATE_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 /var/log/ninjasre
install -d -m 0750 /etc/ninjasre
chgrp "${SERVICE_USER}" /etc/ninjasre

log "system installation complete"

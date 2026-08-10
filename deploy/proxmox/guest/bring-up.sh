#!/bin/sh
#
# Install the platform into the guest and start it under the guest's own init.
#
# Runs in the guest, after install-system.sh has provided PostgreSQL and a
# Python interpreter. `/bin/sh`, for the reason the other guest script gives.
#
# Three processes, matching the topology the platform declares for itself: the
# credential proxy, the application, and the console. The proxy is a separate
# process rather than a thread of the application for the same reason it is a
# separate container in the Compose profiles — it is the only one holding a
# credential, so it gets its own account boundary and its own service to stop.
#
# Configured through the environment, because it is invoked by `pct exec` and a
# flag list would be quoted twice.
#
#   NINJASRE_PROFILE        dev | homelab | standard | enterprise
#   NINJASRE_SOURCE_DIR     the source tree inside the guest
#   NINJASRE_API_PORT       the application's port
#   NINJASRE_CONSOLE_PORT   the console's port
#   NINJASRE_BIND_ADDRESS   the address both bind to
#   NINJASRE_SEED_ENV       optional environment file to start from
#   NINJASRE_PROVIDER       model provider, and the credential or endpoint for it
#   NINJASRE_PROVIDER_KEY
#   NINJASRE_PROVIDER_URL
#   NINJASRE_PROVIDER_MODEL

set -eu

PROFILE="${NINJASRE_PROFILE:-homelab}"
SOURCE_DIR="${NINJASRE_SOURCE_DIR:-/opt/ninjasre/src}"
API_PORT="${NINJASRE_API_PORT:-8420}"
CONSOLE_PORT="${NINJASRE_CONSOLE_PORT:-8421}"
PROXY_PORT="${NINJASRE_PROXY_PORT:-8422}"
BIND_ADDRESS="${NINJASRE_BIND_ADDRESS:-0.0.0.0}"
SEED_ENV="${NINJASRE_SEED_ENV:-}"
PROVIDER="${NINJASRE_PROVIDER:-}"
PROVIDER_KEY="${NINJASRE_PROVIDER_KEY:-}"
PROVIDER_URL="${NINJASRE_PROVIDER_URL:-}"
PROVIDER_MODEL="${NINJASRE_PROVIDER_MODEL:-}"

VENV="/opt/ninjasre/venv"
ENV_FILE="/etc/ninjasre/ninjasre.env"
STATE_DIR="/var/lib/ninjasre"
SERVICE_USER="ninjasre"
DB_NAME="ninjasre"
DB_USER="ninjasre"

log() { printf '    [guest] %s\n' "$*"; }
die() { printf '    [guest] fail: %s\n' "$*" >&2; exit 1; }

DISTRO="$(. /etc/os-release && printf '%s' "${ID}")"
[ -d "${SOURCE_DIR}" ] || die "no source tree at ${SOURCE_DIR}"

# --- The virtual environment -------------------------------------------------
#
# Its own environment rather than the system interpreter, so an upgrade of the
# guest's Python packages cannot change what the platform is running against.

# The interpreter install-system.sh fetched, not the distribution's. Reading it
# from the file it wrote is what keeps the two halves from disagreeing about
# which Python the deployment runs.
PYTHON_PATH_FILE="/opt/ninjasre/python-path"
if [ -r "${PYTHON_PATH_FILE}" ]; then
    PYTHON="$(cat "${PYTHON_PATH_FILE}")"
else
    die "no interpreter recorded at ${PYTHON_PATH_FILE} — run install-system.sh first"
fi
[ -x "${PYTHON}" ] || die "the recorded interpreter ${PYTHON} is not executable"

log "installing the platform into ${VENV} (Python $("${PYTHON}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"
"${PYTHON}" -m venv "${VENV}"
"${VENV}/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true
"${VENV}/bin/pip" install --quiet --no-cache-dir "${SOURCE_DIR}" >/tmp/pip-install.log 2>&1 \
    || { tail -25 /tmp/pip-install.log >&2; die "the platform did not install"; }

# The package directory the platform lives in shares a name with a module in
# Python's own standard library, and the standard library wins unless something
# is put ahead of it. Every entry point below therefore runs with this on
# PYTHONPATH; without it the first import fails with a message that blames the
# platform's own module rather than the shadowing.
SITE_PACKAGES="$("${VENV}/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
"${VENV}/bin/python" -c 'import platform.startup' 2>/dev/null \
    && log "note: the interpreter resolved the platform package without help" || true
PYTHONPATH="${SITE_PACKAGES}" "${VENV}/bin/python" -c 'import platform.startup' \
    || die "the installed platform package cannot be imported even with PYTHONPATH set"

log "installed $("${VENV}/bin/pip" show ninjasre 2>/dev/null | awk '/^Version:/ {print $2}')"

# --- The database ------------------------------------------------------------
#
# Created here rather than by the application, because creating a role and
# installing extensions are superuser operations, and a running application
# should not be able to perform either.

psql_super() { su postgres -c "psql --no-psqlrc --quiet --tuples-only --command \"$1\" ${2:-postgres}"; }

# The role's password is rotated exactly when a new configuration file is about
# to be written, and never otherwise. Rotating it while an existing file still
# holds the old one would leave a deployment that cannot reach its own database;
# refusing to rotate when the file is gone would leave an operator with a role
# whose password nobody knows. Which of the two is happening is decided here,
# before either the role or the file is touched.
if [ -f "${ENV_FILE}" ]; then
    DB_PASSWORD=""
else
    DB_PASSWORD="$(openssl rand -hex 24)"
fi

if [ "$(su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"")" = "1" ]; then
    if [ -n "${DB_PASSWORD}" ]; then
        log "the ${DB_USER} role exists and no configuration does — setting a new password"
        psql_super "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASSWORD}'"
    fi
else
    [ -n "${DB_PASSWORD}" ] || die "the ${DB_USER} role is missing and ${ENV_FILE} holds a password for it — remove the file to rebuild both"
    log "creating the ${DB_USER} role and the ${DB_NAME} database"
    psql_super "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}'"
fi

if [ "$(su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"")" != "1" ]; then
    su postgres -c "createdb --owner=${DB_USER} ${DB_NAME}"
fi

# Both extensions, in the platform's database and in the template every later
# database is made from — so a scratch database created for a restore check has
# them too, rather than failing inside a query.
for database in "${DB_NAME}" template1; do
    psql_super "CREATE EXTENSION IF NOT EXISTS vector" "${database}"
    psql_super "CREATE EXTENSION IF NOT EXISTS age" "${database}"
done
log "extensions present: $(su postgres -c "psql -tAc \"SELECT string_agg(extname || ' ' || extversion, ', ') FROM pg_extension WHERE extname IN ('vector','age')\" ${DB_NAME}")"

# The platform runs `LOAD 'age'` on each connection before it will use the
# graph, and PostgreSQL allows that statement to superusers only — a bare
# library name can never satisfy the `$libdir/plugins` exception, and
# `shared_preload_libraries` does not change the rule. So the role that gets no
# graph is not missing a grant; it is not a superuser.
#
# This is parity, not a relaxation: in the published deployment the account the
# platform connects as is the container cluster's superuser, and has been all
# along. It is called out here because a native install makes it visible.
#
# Removing it is an application change, not a provisioning one: the graph
# bootstrap would have to treat an already-loaded library as loaded instead of
# requiring the statement to succeed.
psql_super "ALTER ROLE ${DB_USER} SUPERUSER"

# --- The configuration -------------------------------------------------------
#
# Written once and never overwritten. A second run must not mint a new
# encryption key: the old one is the only thing that can read what the old one
# wrote, and replacing it silently turns every stored credential into
# ciphertext nobody holds the key for.

if [ -f "${ENV_FILE}" ]; then
    log "keeping the existing ${ENV_FILE} (delete it to regenerate)"
else
    log "writing ${ENV_FILE}"
    if [ -n "${SEED_ENV}" ] && [ -f "${SEED_ENV}" ]; then
        cp "${SEED_ENV}" "${ENV_FILE}"
        log "seeded from the operator's file"
    else
        : >"${ENV_FILE}"
    fi
    chmod 0640 "${ENV_FILE}"
    chgrp "${SERVICE_USER}" "${ENV_FILE}"

    have() { grep -q "^$1=" "${ENV_FILE}"; }
    set_if_absent() { have "$1" || printf '%s="%s"\n' "$1" "$2" >>"${ENV_FILE}"; }

    set_if_absent NINJASRE_DATABASE_URL \
        "postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}"

    # The platform never generates this one, by design: it is the key an
    # operator has to back up separately from their database dumps.
    # Provisioning is the one moment where generating it is right, because the
    # alternative is a deployment that cannot store a credential at all.
    set_if_absent NINJASRE_DATABASE_ENCRYPTION_KEY "$(openssl rand -base64 32)"

    # The first administrator's token is left unset on purpose: the application
    # mints one at first start and prints it once, which leaves no long-lived
    # secret in a file.

    # The model provider, and whichever of a credential or an endpoint that
    # provider takes. One provider credential is the whole minimum viable
    # configuration, and the platform refuses to start without it — so the
    # names are mapped here rather than left for the operator to look up.
    if [ -n "${PROVIDER}" ]; then
        set_if_absent NINJASRE_LLM_PROVIDER "${PROVIDER}"
        [ -n "${PROVIDER_MODEL}" ] && set_if_absent NINJASRE_LLM_MODEL "${PROVIDER_MODEL}"
        case "${PROVIDER}" in
            anthropic) [ -n "${PROVIDER_KEY}" ] && set_if_absent ANTHROPIC_API_KEY "${PROVIDER_KEY}" ;;
            openai) [ -n "${PROVIDER_KEY}" ] && set_if_absent OPENAI_API_KEY "${PROVIDER_KEY}" ;;
            openrouter) [ -n "${PROVIDER_KEY}" ] && set_if_absent OPENROUTER_API_KEY "${PROVIDER_KEY}" ;;
            nvidia_nim) [ -n "${PROVIDER_KEY}" ] && set_if_absent NVIDIA_API_KEY "${PROVIDER_KEY}" ;;
            google_gemini|google_vertex_ai) [ -n "${PROVIDER_KEY}" ] && set_if_absent GOOGLE_API_KEY "${PROVIDER_KEY}" ;;
            azure_openai) [ -n "${PROVIDER_KEY}" ] && set_if_absent AZURE_OPENAI_API_KEY "${PROVIDER_KEY}" ;;
            ollama) [ -n "${PROVIDER_URL}" ] && set_if_absent OLLAMA_BASE_URL "${PROVIDER_URL}" ;;
        esac
    fi

    set_if_absent NINJASRE_DEPLOYMENT_PROFILE "${PROFILE}"
    set_if_absent NINJASRE_STATE_DIR "${STATE_DIR}"
    set_if_absent NINJASRE_CREDENTIAL_PROXY_URL "http://127.0.0.1:${PROXY_PORT}"
    set_if_absent NINJASRE_ENDPOINT "http://127.0.0.1:${API_PORT}"
    set_if_absent NINJASRE_LOG_FORMAT "json"
    set_if_absent PYTHONPATH "${SITE_PACKAGES}"
fi

# --- Migrations --------------------------------------------------------------
#
# Before the services start, not by them. Three processes racing to migrate one
# schema is a failure that only appears under the timing nobody reproduces.

# One provider credential is the whole minimum viable configuration, and the
# platform refuses to start without one — correctly. Stopping here says so in
# one line, instead of letting the operator find it under a migration's output
# with everything already installed and nothing explaining what to do next.
if ! grep -q '^NINJASRE_LLM_PROVIDER=' "${ENV_FILE}"; then
    printf '\n'
    log "the platform is installed, and it is not started."
    log "no model provider is configured, and one is required. Set it:"
    log "  ${ENV_FILE}"
    log "    NINJASRE_LLM_PROVIDER=\"ollama\"        # or anthropic, openai, ..."
    log "    OLLAMA_BASE_URL=\"http://host:11434\"   # or that provider's API key"
    log "then finish the installation by running this script again:"
    log "  ${0}"
    exit 0
fi

log "applying migrations"
su "${SERVICE_USER}" -s /bin/sh -c \
    "cd '${STATE_DIR}' && set -a && . '${ENV_FILE}' && set +a && exec '${VENV}/bin/python' -m gateway.http.serve --migrate-only" \
    || die "the migration step failed"

# --- Services ----------------------------------------------------------------

write_systemd_unit() {
    name="$1"; description="$2"; module="$3"; arguments="$4"
    cat >"/etc/systemd/system/ninjasre-${name}.service" <<EOF
# Written by NinjaSRE provisioning. Edits are lost on re-provision.
[Unit]
Description=NinjaSRE ${description}
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=exec
User=${SERVICE_USER}
Group=${SERVICE_USER}
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${SITE_PACKAGES}
WorkingDirectory=${STATE_DIR}
ExecStart=${VENV}/bin/python -m ${module} ${arguments}
Restart=on-failure
RestartSec=5

# The state directory is the only path this service has any business writing.
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${STATE_DIR} /var/log/ninjasre

[Install]
WantedBy=multi-user.target
EOF
}

write_openrc_service() {
    name="$1"; description="$2"; module="$3"; arguments="$4"
    cat >"/etc/init.d/ninjasre-${name}" <<EOF
#!/sbin/openrc-run
# Written by NinjaSRE provisioning. Edits are lost on re-provision.

description="NinjaSRE ${description}"

# Sourced at the top rather than in start_pre, so the values are exported into
# the environment the supervised process actually gets.
if [ -f "${ENV_FILE}" ]; then
    set -a
    . "${ENV_FILE}"
    set +a
fi
export PYTHONPATH="${SITE_PACKAGES}"

command="${VENV}/bin/python"
command_args="-m ${module} ${arguments}"
command_user="${SERVICE_USER}:${SERVICE_USER}"
command_background=true
directory="${STATE_DIR}"
pidfile="/run/ninjasre-${name}.pid"
output_log="/var/log/ninjasre/${name}.log"
error_log="/var/log/ninjasre/${name}.log"

depend() {
    need net
    use postgresql
}

start_pre() {
    checkpath -d -o ${SERVICE_USER}:${SERVICE_USER} -m 0750 /var/log/ninjasre
}
EOF
    chmod 0755 "/etc/init.d/ninjasre-${name}"
}

install_service() {
    case "${DISTRO}" in
        debian) write_systemd_unit "$@" ;;
        alpine) write_openrc_service "$@" ;;
    esac
}

log "installing the service units"
install_service proxy "credential proxy" \
    "gateway.proxy" "--host 127.0.0.1 --port ${PROXY_PORT}"
install_service app "application" \
    "gateway.http.serve" "--host ${BIND_ADDRESS} --port ${API_PORT}"
install_service console "console" \
    "gateway.http.serve" "--host ${BIND_ADDRESS} --port ${CONSOLE_PORT}"

start_service() {
    case "${DISTRO}" in
        debian) systemctl enable --now "ninjasre-$1" >/dev/null ;;
        alpine)
            rc-update add "ninjasre-$1" default >/dev/null
            rc-service "ninjasre-$1" restart >/dev/null
            ;;
    esac
}

wait_ready() {
    probe="$1"; port="$2"; limit="$3"
    attempt=0
    while [ "${attempt}" -lt "${limit}" ]; do
        if curl -fsS "http://${probe}:${port}/health/ready" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

probe_host="${BIND_ADDRESS}"
[ "${probe_host}" = "0.0.0.0" ] && probe_host="127.0.0.1"

[ "${DISTRO}" = "debian" ] && systemctl daemon-reload

# Ordered, not started in a batch. The application and the console are the same
# ASGI programme on two ports, and each runs the platform's boot sequence — which
# creates the first administrator among other things. Started together they race
# it, and the loser dies on a duplicate key thirteen milliseconds later. The
# Compose profiles express the same ordering with `depends_on`; this is that
# ordering, in a guest that has no compose to express it for it.
log "starting the credential proxy"
start_service proxy

log "starting the application"
start_service app
wait_ready "${probe_host}" "${API_PORT}" 180 || {
    printf '\n'
    case "${DISTRO}" in
        debian) journalctl -u ninjasre-app --no-pager --lines 40 >&2 || true ;;
        alpine) tail -40 /var/log/ninjasre/app.log >&2 || true ;;
    esac
    die "the application was not ready within 180s — the log above is the last 40 lines"
}
log "the application is ready"

log "starting the console"
start_service console

# --- Readiness ---------------------------------------------------------------
#
# Readiness rather than liveness. The two differ while the schema is settling,
# and a provisioning run that reported success on the wrong one would be
# reporting that the process exists.

if wait_ready "${probe_host}" "${CONSOLE_PORT}" 120; then
    log "the console is ready"
    exit 0
fi

printf '\n'
case "${DISTRO}" in
    debian) journalctl -u ninjasre-console --no-pager --lines 40 >&2 || true ;;
    alpine) tail -40 /var/log/ninjasre/console.log >&2 || true ;;
esac
die "the console was not ready within 120s — the log above is the last 40 lines"

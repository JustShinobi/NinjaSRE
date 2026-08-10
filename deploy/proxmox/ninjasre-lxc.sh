#!/usr/bin/env bash
#
# Provision NinjaSRE into an LXC container on a Proxmox VE node.
#
# Run this on the node, as root. It creates the container, installs PostgreSQL
# and the platform inside it, and starts the services. One command, and the
# operator's only required decision is which distribution the container runs.
#
#     ./ninjasre-lxc.sh --distro debian --ip dhcp
#     ./ninjasre-lxc.sh --distro alpine --ip 192.168.68.60/24 --gateway 192.168.68.1
#
# Everything runs directly in the guest: PostgreSQL under the guest's own init,
# the platform's three processes under systemd or OpenRC. No container runtime
# and no images — an LXC container is already the isolation boundary, and
# nesting a second one inside it would buy nothing this deployment needs.
#
# What that costs is a graph extension neither distribution packages, compiled
# here against a pinned PostgreSQL major version. What it buys is a guest an
# operator can read: three services, one configuration file, one database.
#
# What it will not do: it never deletes a container it did not create in this
# run unless `--force` says so, and it never starts without either a template
# already on the node or permission to download one.

set -euo pipefail

# --- Defaults ----------------------------------------------------------------
#
# Every one of these is overridable by a flag or by a config file. They are
# named here rather than inline so `--help` and the contract test read the same
# values the run uses.

SUPPORTED_DISTROS="alpine debian"
SUPPORTED_PROFILES="dev homelab standard enterprise"

# The providers the platform knows. Validated here so a typo fails before a
# container exists rather than after everything is installed.
SUPPORTED_LLM_PROVIDERS="anthropic openai azure_openai aws_bedrock google_gemini google_vertex_ai openrouter nvidia_nim ollama"

DEFAULT_DISTRO="debian"

# The deployment shape. `homelab` rather than `standard` because it is the only
# profile that declares a resource ceiling and enforces it, which is what a
# first deployment beside somebody's existing workloads needs.
DEFAULT_PROFILE="homelab"

DEFAULT_HOSTNAME="ninjasre"

# `nesting` is what lets an unprivileged container mount its own /proc and /sys
# views, which systemd needs to manage services at all. `keyctl` keeps the
# session keyring from leaking into the host's — cheap, and it is the pair a
# guest running real services wants.
DEFAULT_FEATURES="nesting=1,keyctl=1"

# Above the profile's own ceiling, not equal to it. The platform is capped at
# four gibibytes; compiling the graph extension against PostgreSQL is the peak
# and it happens before anything is running.
DEFAULT_MEMORY_MIB="6144"
DEFAULT_SWAP_MIB="2048"
DEFAULT_CORES="4"
DEFAULT_ROOTFS_GIB="32"

DEFAULT_STORAGE="local-lvm"
DEFAULT_TEMPLATE_STORAGE="local"
DEFAULT_BRIDGE="vmbr0"
DEFAULT_IP="dhcp"
DEFAULT_NAMESERVER=""
DEFAULT_SEARCHDOMAIN=""
DEFAULT_VLAN=""
DEFAULT_UNPRIVILEGED="1"
DEFAULT_ONBOOT="1"

DEFAULT_API_PORT="8420"
DEFAULT_CONSOLE_PORT="8421"

# What the application and console bind to inside the guest. Loopback is right
# when a reverse proxy fronts them; a container on its own IP that nobody can
# reach is not, so this flow binds to every interface of the guest and leaves
# the network boundary to the bridge and the firewall. The credential proxy is
# never in this decision — it binds to loopback always.
DEFAULT_BIND_ADDRESS="0.0.0.0"

DEFAULT_GUEST_ROOT="/opt/ninjasre"

# Templates. Pinned to a major release rather than "latest available", because a
# provisioning script whose base image moves under it is one whose failures are
# not reproducible. Override with --template.
DEFAULT_DEBIAN_TEMPLATE_PATTERN="debian-13-standard"
DEFAULT_ALPINE_TEMPLATE_PATTERN="alpine-3.23-default"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# --- Resolved settings -------------------------------------------------------

DISTRO="${DEFAULT_DISTRO}"
PROFILE="${DEFAULT_PROFILE}"
CT_HOSTNAME="${DEFAULT_HOSTNAME}"
FEATURES="${DEFAULT_FEATURES}"
MEMORY_MIB="${DEFAULT_MEMORY_MIB}"
SWAP_MIB="${DEFAULT_SWAP_MIB}"
CORES="${DEFAULT_CORES}"
ROOTFS_GIB="${DEFAULT_ROOTFS_GIB}"
STORAGE="${DEFAULT_STORAGE}"
TEMPLATE_STORAGE="${DEFAULT_TEMPLATE_STORAGE}"
BRIDGE="${DEFAULT_BRIDGE}"
IP_ADDRESS="${DEFAULT_IP}"
GATEWAY=""
NAMESERVER="${DEFAULT_NAMESERVER}"
SEARCHDOMAIN="${DEFAULT_SEARCHDOMAIN}"
VLAN="${DEFAULT_VLAN}"
UNPRIVILEGED="${DEFAULT_UNPRIVILEGED}"
ONBOOT="${DEFAULT_ONBOOT}"
API_PORT="${DEFAULT_API_PORT}"
CONSOLE_PORT="${DEFAULT_CONSOLE_PORT}"
BIND_ADDRESS="${DEFAULT_BIND_ADDRESS}"
GUEST_ROOT="${DEFAULT_GUEST_ROOT}"

VMID=""
PASSWORD=""
LLM_PROVIDER=""
LLM_MODEL=""
LLM_API_KEY=""
LLM_BASE_URL=""
TEMPLATE=""
TARGET_NODE=""
SOURCE_SPEC=""
SOURCE_REF="HEAD"
ENV_FILE=""
SSH_PUBKEY=""
TAGS="ninjasre"

CHECK_ONLY="0"
DRY_RUN="0"
FORCE="0"
ASSUME_YES="0"
DOWNLOAD_TEMPLATE="1"
START_STACK="1"

# --- Output ------------------------------------------------------------------

if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
else
    C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""
fi

log()  { printf '%s==>%s %s\n' "${C_BOLD}" "${C_RESET}" "$*"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '%s  ok%s %s\n' "${C_GREEN}" "${C_RESET}" "$*"; }
warn() { printf '%swarn%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*" >&2; }
die()  { printf '%s fail%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2; exit 1; }

run() {
    if [[ "${DRY_RUN}" == "1" ]]; then
        printf '%s     $ %s%s\n' "${C_DIM}" "$*" "${C_RESET}"
        return 0
    fi
    "$@"
}

usage() {
    cat <<'USAGE'
Provision NinjaSRE into a Proxmox LXC container.

Usage: ninjasre-lxc.sh [options]

Container
  --vmid N                 Container ID. Default: the cluster's next free ID.
  --hostname NAME          Container hostname. Default: ninjasre
  --distro debian|alpine   Guest distribution. Default: debian
  --template VOLID         Explicit template volume, e.g. local:vztmpl/....tar.zst
  --template-storage NAME  Where templates live and are downloaded. Default: local
  --no-download            Fail rather than download a missing template.
  --storage NAME           Root filesystem storage. Default: local-lvm
  --rootfs-size GIB        Root filesystem size. Default: 32
  --cores N                CPU cores. Default: 4
  --memory MIB             Memory. Default: 6144
  --swap MIB               Swap. Default: 2048
  --privileged             Create a privileged container. Default: unprivileged.
  --features LIST          Override the LXC feature list. Default: nesting=1,keyctl=1
  --password SECRET        Root password in the guest. Default: none (console via pct).
  --ssh-key PATH           Public key authorised for root in the guest.
  --tags LIST              Proxmox tags, semicolon separated. Default: ninjasre
  --no-onboot              Do not start the container with the node.

Network
  --bridge NAME            Bridge. Default: vmbr0
  --vlan TAG               VLAN tag on the bridge. Default: untagged.
  --ip dhcp|CIDR           Address. Default: dhcp
  --gateway ADDRESS        Gateway. Required with a static address.
  --nameserver LIST        Resolvers. Default: inherited from the node.
  --searchdomain NAME      Search domain. Default: inherited from the node.

Application
  --profile NAME           dev | homelab | standard | enterprise. Default: homelab
  --api-port N             Published API port. Default: 8420
  --console-port N         Published console port. Default: 8421
  --bind-address ADDR      Address app and console bind to. Default: 0.0.0.0
  --env-file PATH          An environment file to seed with. Missing secrets are generated.

Model provider
  One provider credential is the whole minimum viable configuration, and the
  platform will not start without it. Give it here, or in --env-file, or set it
  in the guest afterwards and re-run the guest's bring-up.sh.

  --llm-provider NAME      anthropic, openai, ollama, openrouter, ...
  --llm-model ID           Which model, when the configuration names none.
  --llm-api-key SECRET     That provider's key, for the providers that take one.
  --llm-base-url URL       That provider's endpoint, for the ones that take one.
  --source SPEC            Where the source comes from:
                             dir:PATH   a checkout on this node (default: this repository)
                             tar:PATH   a tarball on this node
                             git:URL    cloned in the guest
  --source-ref REF         Ref for git: and dir: sources. Default: HEAD
  --no-start               Create the container and install the system, but do
                           not install the platform or start the services.

Flow
  --node NAME              Provision on another node of the cluster, over SSH.
  --config PATH            Read these settings from a file first (see the example).
  --check-only             Run the preflight checks and stop.
  --dry-run                Print what would run, change nothing.
  --force                  Destroy an existing container with this ID first.
  --yes                    Do not prompt.
  -h, --help               This text.
USAGE
}

# --- Argument parsing --------------------------------------------------------
#
# The config file is read first and flags win, so an operator can keep a file
# per deployment and still override one value on the command line.

load_config() {
    local path="$1"
    [[ -r "${path}" ]] || die "config file not readable: ${path}"
    # Only KEY=VALUE lines, sourced in a subshell-free way but with a guard: a
    # config file is operator-owned, so this is deliberately a plain source
    # after a shape check rather than a parser nobody would maintain.
    if grep -Ev '^[[:space:]]*(#|$)' "${path}" | grep -qvE '^[A-Z_]+=.*$'; then
        die "config file has lines that are not KEY=VALUE: ${path}"
    fi
    # shellcheck disable=SC1090
    source "${path}"
}

parse_args() {
    local args=("$@")
    # A first pass for --config only, so file values are in place before the
    # flags that must override them are applied.
    local index
    for ((index = 0; index < ${#args[@]}; index++)); do
        if [[ "${args[index]}" == "--config" ]]; then
            load_config "${args[index + 1]:-}"
        fi
    done

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --vmid) VMID="$2"; shift 2 ;;
            --hostname) CT_HOSTNAME="$2"; shift 2 ;;
            --distro) DISTRO="$2"; shift 2 ;;
            --template) TEMPLATE="$2"; shift 2 ;;
            --template-storage) TEMPLATE_STORAGE="$2"; shift 2 ;;
            --no-download) DOWNLOAD_TEMPLATE="0"; shift ;;
            --storage) STORAGE="$2"; shift 2 ;;
            --rootfs-size) ROOTFS_GIB="$2"; shift 2 ;;
            --cores) CORES="$2"; shift 2 ;;
            --memory) MEMORY_MIB="$2"; shift 2 ;;
            --swap) SWAP_MIB="$2"; shift 2 ;;
            --privileged) UNPRIVILEGED="0"; shift ;;
            --features) FEATURES="$2"; shift 2 ;;
            --password) PASSWORD="$2"; shift 2 ;;
            --ssh-key) SSH_PUBKEY="$2"; shift 2 ;;
            --tags) TAGS="$2"; shift 2 ;;
            --no-onboot) ONBOOT="0"; shift ;;
            --bridge) BRIDGE="$2"; shift 2 ;;
            --vlan) VLAN="$2"; shift 2 ;;
            --ip) IP_ADDRESS="$2"; shift 2 ;;
            --gateway) GATEWAY="$2"; shift 2 ;;
            --nameserver) NAMESERVER="$2"; shift 2 ;;
            --searchdomain) SEARCHDOMAIN="$2"; shift 2 ;;
            --profile) PROFILE="$2"; shift 2 ;;
            --api-port) API_PORT="$2"; shift 2 ;;
            --console-port) CONSOLE_PORT="$2"; shift 2 ;;
            --bind-address) BIND_ADDRESS="$2"; shift 2 ;;
            --env-file) ENV_FILE="$2"; shift 2 ;;
            --llm-provider) LLM_PROVIDER="$2"; shift 2 ;;
            --llm-model) LLM_MODEL="$2"; shift 2 ;;
            --llm-api-key) LLM_API_KEY="$2"; shift 2 ;;
            --llm-base-url) LLM_BASE_URL="$2"; shift 2 ;;
            --source) SOURCE_SPEC="$2"; shift 2 ;;
            --source-ref) SOURCE_REF="$2"; shift 2 ;;
            --no-start) START_STACK="0"; shift ;;
            --node) TARGET_NODE="$2"; shift 2 ;;
            --config) shift 2 ;;
            --check-only) CHECK_ONLY="1"; shift ;;
            --dry-run) DRY_RUN="1"; shift ;;
            --force) FORCE="1"; shift ;;
            --yes|-y) ASSUME_YES="1"; shift ;;
            -h|--help) usage; exit 0 ;;
            *) die "unknown option: $1 (try --help)" ;;
        esac
    done
}

validate_choices() {
    grep -qw -- "${DISTRO}" <<<"${SUPPORTED_DISTROS}" \
        || die "--distro must be one of: ${SUPPORTED_DISTROS}"
    grep -qw -- "${PROFILE}" <<<"${SUPPORTED_PROFILES}" \
        || die "--profile must be one of: ${SUPPORTED_PROFILES}"
    if [[ "${IP_ADDRESS}" != "dhcp" && -z "${GATEWAY}" ]]; then
        die "a static --ip needs a --gateway"
    fi
    if [[ "${IP_ADDRESS}" != "dhcp" && "${IP_ADDRESS}" != */* ]]; then
        die "--ip needs a prefix length, e.g. 192.168.68.60/24"
    fi
    [[ -z "${ENV_FILE}" || -r "${ENV_FILE}" ]] || die "--env-file not readable: ${ENV_FILE}"
    [[ -z "${SSH_PUBKEY}" || -r "${SSH_PUBKEY}" ]] || die "--ssh-key not readable: ${SSH_PUBKEY}"
}

# --- Preflight ---------------------------------------------------------------

preflight() {
    log "Preflight on $(hostname)"

    [[ "${EUID}" -eq 0 ]] || die "run as root on the Proxmox node"
    command -v pct >/dev/null || die "pct not found — this is not a Proxmox VE node"
    command -v pvesm >/dev/null || die "pvesm not found — this is not a Proxmox VE node"
    ok "Proxmox VE $(pveversion | sed 's|pve-manager/||; s|/.*||')"

    if ! pvesm status --storage "${STORAGE}" >/dev/null 2>&1; then
        die "storage '${STORAGE}' does not exist on this node"
    fi
    if ! grep -A5 -E "^[a-z]+: ${STORAGE}\$" /etc/pve/storage.cfg | grep -q "rootdir"; then
        die "storage '${STORAGE}' does not hold container root filesystems (needs content 'rootdir')"
    fi
    ok "storage ${STORAGE} accepts container root filesystems"

    [[ -d "/sys/class/net/${BRIDGE}" ]] || die "bridge '${BRIDGE}' does not exist on this node"
    ok "bridge ${BRIDGE} present"

    local available_mib
    available_mib="$(awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo)"
    if (( available_mib < MEMORY_MIB )); then
        warn "node has ${available_mib} MiB available and the container asks for ${MEMORY_MIB} MiB"
        warn "the build step is the peak; lower --memory or free some first"
    else
        ok "node has ${available_mib} MiB available for a ${MEMORY_MIB} MiB container"
    fi

    if [[ -z "${VMID}" ]]; then
        VMID="$(pvesh get /cluster/nextid)"
        info "allocated container ID ${VMID}"
    elif pct status "${VMID}" >/dev/null 2>&1; then
        if [[ "${FORCE}" == "1" ]]; then
            warn "container ${VMID} exists and --force will destroy it"
        else
            die "container ${VMID} already exists (use --force to replace it)"
        fi
    fi
    ok "container ID ${VMID}"

    resolve_template
    ok "template ${TEMPLATE}"

    resolve_source
    ok "source ${SOURCE_SPEC}"
}

resolve_template() {
    if [[ -n "${TEMPLATE}" ]]; then
        return
    fi

    local pattern
    case "${DISTRO}" in
        debian) pattern="${DEFAULT_DEBIAN_TEMPLATE_PATTERN}" ;;
        alpine) pattern="${DEFAULT_ALPINE_TEMPLATE_PATTERN}" ;;
        *) die "no template pattern for ${DISTRO}" ;;
    esac

    local present
    present="$(pveam list "${TEMPLATE_STORAGE}" 2>/dev/null | awk -v p="${pattern}" '$1 ~ p {print $1}' | sort | tail -1)"
    if [[ -n "${present}" ]]; then
        TEMPLATE="${present}"
        return
    fi

    local candidate
    candidate="$(pveam available --section system 2>/dev/null | awk -v p="${pattern}" '$2 ~ p {print $2}' | sort | tail -1)"
    [[ -n "${candidate}" ]] || die "no template matching '${pattern}'; pass --template explicitly"

    if [[ "${DOWNLOAD_TEMPLATE}" != "1" ]]; then
        die "template '${candidate}' is not on ${TEMPLATE_STORAGE} and --no-download was given"
    fi

    log "Downloading template ${candidate}"
    run pveam download "${TEMPLATE_STORAGE}" "${candidate}"
    TEMPLATE="${TEMPLATE_STORAGE}:vztmpl/${candidate}"
}

# Where the source tree comes from. The default is this repository, because the
# common case is an operator who cloned it onto the node and ran the script out
# of it. `git:` is for the node that has no checkout, and it is the only mode
# that needs the guest to reach a forge.
resolve_source() {
    if [[ -n "${SOURCE_SPEC}" ]]; then
        case "${SOURCE_SPEC}" in
            dir:*|tar:*|git:*) ;;
            *) die "--source must start with dir:, tar: or git:" ;;
        esac
        local path="${SOURCE_SPEC#*:}"
        case "${SOURCE_SPEC}" in
            dir:*) [[ -d "${path}" ]] || die "--source dir does not exist: ${path}" ;;
            tar:*) [[ -r "${path}" ]] || die "--source tarball not readable: ${path}" ;;
        esac
        return
    fi

    local repo_root="${SCRIPT_DIR}/../.."
    if [[ -f "${repo_root}/pyproject.toml" ]]; then
        SOURCE_SPEC="dir:$(cd -- "${repo_root}" && pwd)"
        return
    fi
    die "no repository next to this script; pass --source dir:PATH, tar:PATH or git:URL"
}

# --- Source bundle -----------------------------------------------------------
#
# `git archive` when the directory is a checkout, because it applies the
# repository's own ignore rules and so cannot sweep a virtualenv, a node_modules
# or somebody's .env into the container. The tar fallback excludes the same
# things by name for the directory that is not a checkout.

BUNDLE=""

make_bundle() {
    case "${SOURCE_SPEC}" in
        git:*) return ;;
        tar:*) BUNDLE="${SOURCE_SPEC#tar:}"; return ;;
    esac

    local directory="${SOURCE_SPEC#dir:}"
    BUNDLE="$(mktemp -t ninjasre-source-XXXXXX.tar.gz)"

    log "Bundling ${directory}"
    if git -C "${directory}" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "${directory}" archive --format=tar.gz --output="${BUNDLE}" "${SOURCE_REF}"
        info "from git archive at ${SOURCE_REF}"
        # A committed ref is what deploys, which is the right default and the
        # wrong surprise. An operator testing an uncommitted change would
        # otherwise watch a build of code they did not write.
        if ! git -C "${directory}" diff --quiet HEAD 2>/dev/null; then
            warn "the working tree has uncommitted changes and they are NOT in this bundle"
            warn "commit them, or pass --source tar:PATH with a bundle of your own"
        fi
    else
        tar --create --gzip --file "${BUNDLE}" \
            --exclude='.git' --exclude='.venv' --exclude='node_modules' \
            --exclude='.next' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
            --directory "${directory}" .
        info "from a plain tar of the working tree"
    fi
    info "$(du -h "${BUNDLE}" | cut -f1) bundle"
}

cleanup() {
    if [[ -n "${BUNDLE}" && "${SOURCE_SPEC}" == dir:* && -f "${BUNDLE}" ]]; then
        rm -f "${BUNDLE}"
    fi
}
trap cleanup EXIT

# --- Creation ----------------------------------------------------------------

create_container() {
    if [[ "${FORCE}" == "1" ]] && pct status "${VMID}" >/dev/null 2>&1; then
        log "Destroying container ${VMID}"
        run pct stop "${VMID}" >/dev/null 2>&1 || true
        run pct destroy "${VMID}" --purge
    fi

    local net="name=eth0,bridge=${BRIDGE},firewall=1"
    [[ -n "${VLAN}" ]] && net="${net},tag=${VLAN}"
    if [[ "${IP_ADDRESS}" == "dhcp" ]]; then
        net="${net},ip=dhcp"
    else
        net="${net},ip=${IP_ADDRESS},gw=${GATEWAY}"
    fi

    local -a create=(
        pct create "${VMID}" "${TEMPLATE}"
        --hostname "${CT_HOSTNAME}"
        --ostype "${DISTRO}"
        --arch amd64
        --cores "${CORES}"
        --memory "${MEMORY_MIB}"
        --swap "${SWAP_MIB}"
        --rootfs "${STORAGE}:${ROOTFS_GIB}"
        --features "${FEATURES}"
        --unprivileged "${UNPRIVILEGED}"
        --onboot "${ONBOOT}"
        --net0 "${net}"
        --tags "${TAGS}"
        --description "NinjaSRE ${PROFILE} profile, provisioned by deploy/proxmox/ninjasre-lxc.sh"
    )
    [[ -n "${NAMESERVER}" ]] && create+=(--nameserver "${NAMESERVER}")
    [[ -n "${SEARCHDOMAIN}" ]] && create+=(--searchdomain "${SEARCHDOMAIN}")
    [[ -n "${PASSWORD}" ]] && create+=(--password "${PASSWORD}")
    [[ -n "${SSH_PUBKEY}" ]] && create+=(--ssh-public-keys "${SSH_PUBKEY}")

    log "Creating container ${VMID} (${DISTRO}, ${CORES} cores, ${MEMORY_MIB} MiB)"
    run "${create[@]}"

    log "Starting container ${VMID}"
    run pct start "${VMID}"
    wait_for_network
}

wait_for_network() {
    [[ "${DRY_RUN}" == "1" ]] && return 0

    log "Waiting for the container's network"
    local attempt
    for attempt in $(seq 1 60); do
        if pct exec "${VMID}" -- ping -c1 -W1 1.1.1.1 >/dev/null 2>&1; then
            ok "container reaches the network after ${attempt}s"
            return 0
        fi
        sleep 1
    done
    die "container ${VMID} has no network after 60s — check the bridge, VLAN and gateway"
}

container_address() {
    pct exec "${VMID}" -- ip -4 -o addr show dev eth0 2>/dev/null \
        | awk '{print $4}' | cut -d/ -f1 | head -1
}

# --- Installation ------------------------------------------------------------

install_into_container() {
    log "Pushing the installer into the container"
    run pct exec "${VMID}" -- mkdir -p "${GUEST_ROOT}/bin" "${GUEST_ROOT}/src"
    run pct push "${VMID}" "${SCRIPT_DIR}/guest/install-system.sh" "${GUEST_ROOT}/bin/install-system.sh" --perms 0755
    run pct push "${VMID}" "${SCRIPT_DIR}/guest/bring-up.sh" "${GUEST_ROOT}/bin/bring-up.sh" --perms 0755

    log "Installing PostgreSQL and the extensions (${DISTRO}, several minutes)"
    run pct exec "${VMID}" -- "${GUEST_ROOT}/bin/install-system.sh" --distro "${DISTRO}"

    case "${SOURCE_SPEC}" in
        git:*)
            log "Cloning the source in the container"
            run pct exec "${VMID}" -- sh -c \
                "rm -rf '${GUEST_ROOT}/src' && git clone --depth 1 --branch '${SOURCE_REF}' '${SOURCE_SPEC#git:}' '${GUEST_ROOT}/src'"
            ;;
        *)
            log "Pushing the source into the container"
            run pct push "${VMID}" "${BUNDLE}" "${GUEST_ROOT}/source.tar.gz" --perms 0600
            run pct exec "${VMID}" -- sh -c \
                "rm -rf '${GUEST_ROOT}/src' && mkdir -p '${GUEST_ROOT}/src' && tar -xzf '${GUEST_ROOT}/source.tar.gz' -C '${GUEST_ROOT}/src' && rm -f '${GUEST_ROOT}/source.tar.gz'"
            ;;
    esac

    if [[ -n "${ENV_FILE}" ]]; then
        log "Seeding the deployment's environment"
        run pct push "${VMID}" "${ENV_FILE}" "${GUEST_ROOT}/seed.env" --perms 0600
    fi
}

bring_stack_up() {
    if [[ "${START_STACK}" != "1" ]]; then
        warn "--no-start: the system is installed but the platform is not"
        return 0
    fi

    log "Installing the platform and starting its services"
    local -a environment=(
        "NINJASRE_PROFILE=${PROFILE}"
        "NINJASRE_SOURCE_DIR=${GUEST_ROOT}/src"
        "NINJASRE_API_PORT=${API_PORT}"
        "NINJASRE_CONSOLE_PORT=${CONSOLE_PORT}"
        "NINJASRE_BIND_ADDRESS=${BIND_ADDRESS}"
    )
    [[ -n "${ENV_FILE}" ]] && environment+=("NINJASRE_SEED_ENV=${GUEST_ROOT}/seed.env")
    [[ -n "${LLM_PROVIDER}" ]] && environment+=("NINJASRE_PROVIDER=${LLM_PROVIDER}")
    [[ -n "${LLM_MODEL}" ]] && environment+=("NINJASRE_PROVIDER_MODEL=${LLM_MODEL}")
    [[ -n "${LLM_API_KEY}" ]] && environment+=("NINJASRE_PROVIDER_KEY=${LLM_API_KEY}")
    [[ -n "${LLM_BASE_URL}" ]] && environment+=("NINJASRE_PROVIDER_URL=${LLM_BASE_URL}")

    run pct exec "${VMID}" -- env "${environment[@]}" "${GUEST_ROOT}/bin/bring-up.sh"
}

summarise() {
    [[ "${DRY_RUN}" == "1" ]] && { log "Dry run: nothing was created."; return 0; }

    local address
    address="$(container_address)"
    [[ -n "${address}" ]] || address="<container ${VMID}>"

    printf '\n'
    log "NinjaSRE is provisioned"
    info "container   ${VMID} (${CT_HOSTNAME}, ${DISTRO}, profile ${PROFILE})"
    info "address     ${address}"
    if [[ "${START_STACK}" == "1" ]]; then
        info "console     http://${address}:${CONSOLE_PORT}"
        info "api         http://${address}:${API_PORT}"
    fi
    printf '\n'
    info "shell       pct enter ${VMID}"
    if [[ "${DISTRO}" == "alpine" ]]; then
        info "services    pct exec ${VMID} -- rc-service ninjasre-app status"
        info "logs        pct exec ${VMID} -- tail -f /var/log/ninjasre/app.log"
    else
        info "services    pct exec ${VMID} -- systemctl status ninjasre-app"
        info "logs        pct exec ${VMID} -- journalctl -u ninjasre-app -f"
    fi
    info "config      pct exec ${VMID} -- cat /etc/ninjasre/ninjasre.env"
    printf '\n'
    warn "back up NINJASRE_DATABASE_ENCRYPTION_KEY from that file before you store a credential"
    warn "nothing else can decrypt what it wrote, and it is not in your database dumps"
}

# --- Remote node -------------------------------------------------------------
#
# `pct create` is local to a node, so provisioning the other half of the cluster
# means running this script over there. It ships itself and the source bundle
# rather than assuming the repository exists on both machines.

delegate_to_node() {
    local node="$1"; shift
    log "Delegating to node ${node}"

    local remote="/tmp/ninjasre-proxmox.$$"
    make_bundle

    run ssh "root@${node}" "mkdir -p '${remote}/guest'"
    run scp -q "${SCRIPT_DIR}/ninjasre-lxc.sh" "root@${node}:${remote}/"
    run scp -q "${SCRIPT_DIR}/guest/install-system.sh" "${SCRIPT_DIR}/guest/bring-up.sh" "root@${node}:${remote}/guest/"
    run scp -q "${BUNDLE}" "root@${node}:${remote}/source.tar.gz"
    if [[ -n "${ENV_FILE}" ]]; then
        run scp -q "${ENV_FILE}" "root@${node}:${remote}/seed.env"
    fi

    local -a forwarded=()
    local argument
    local skip_next="0"
    for argument in "$@"; do
        if [[ "${skip_next}" == "1" ]]; then skip_next="0"; continue; fi
        case "${argument}" in
            --node) skip_next="1" ;;
            --source|--env-file) skip_next="1" ;;
            *) forwarded+=("${argument}") ;;
        esac
    done
    forwarded+=(--source "tar:${remote}/source.tar.gz")
    [[ -n "${ENV_FILE}" ]] && forwarded+=(--env-file "${remote}/seed.env")

    # The remote command is composed here on purpose, and every interpolated
    # argument goes through %q above.
    # shellcheck disable=SC2029
    run ssh -t "root@${node}" "chmod +x '${remote}/ninjasre-lxc.sh' '${remote}/guest/'*.sh && '${remote}/ninjasre-lxc.sh' $(printf '%q ' "${forwarded[@]}"); status=\$?; rm -rf '${remote}'; exit \$status"
}

confirm() {
    [[ "${ASSUME_YES}" == "1" || "${DRY_RUN}" == "1" ]] && return 0
    printf '\nCreate container %s on %s? [y/N] ' "${VMID}" "$(hostname)"
    local answer
    read -r answer
    [[ "${answer}" == "y" || "${answer}" == "Y" ]] || die "cancelled"
}

main() {
    parse_args "$@"
    validate_choices

    if [[ -n "${LLM_PROVIDER}" ]] && ! grep -qw -- "${LLM_PROVIDER}" <<<"${SUPPORTED_LLM_PROVIDERS}"; then
        die "--llm-provider must be one of: ${SUPPORTED_LLM_PROVIDERS}"
    fi

    if [[ -n "${TARGET_NODE}" && "${TARGET_NODE}" != "$(hostname)" ]]; then
        resolve_source
        delegate_to_node "${TARGET_NODE}" "$@"
        exit 0
    fi

    preflight
    if [[ "${CHECK_ONLY}" == "1" ]]; then
        log "Preflight only — nothing was created."
        exit 0
    fi

    confirm
    make_bundle
    create_container
    install_into_container
    bring_stack_up
    summarise
}

main "$@"

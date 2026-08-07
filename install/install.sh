#!/bin/sh
# NinjaSRE installer for macOS and Linux.
#
# Four properties, and each one is a decision:
#
#   1. No elevated privileges. Ever. A tool that asks for root to install
#      itself is a tool a regulated operator cannot install at all, and
#      "curl | sudo sh" is the pattern their security team has already banned.
#
#   2. A user-local fallback with an exact PATH instruction. When no directory
#      on PATH is writable, this installs to ~/.local/bin and prints the one
#      line to add — for the shell that is actually running, not a generic
#      "add it to your profile".
#
#   3. Integrity verification. The archive's SHA-256 is checked against a
#      published checksum before anything is unpacked. A download that could
#      not be verified is not installed.
#
#   4. No telemetry. This script reports nothing, anywhere. It does not phone
#      home to count installs, check a version, or record a failure.
#
# POSIX sh. Not bash: the shell present on a minimal container image is the one
# somebody will run this with.

set -eu

APP_NAME="ninjasre"
RELEASE_BASE="${NINJASRE_RELEASE_BASE:-https://get.ninjasre.dev}"
VERSION="${NINJASRE_VERSION:-latest}"

# Where to install, in order of preference. The first writable one wins; if
# none is, the fallback below is used and the PATH instruction is printed.
FALLBACK_DIR="${HOME}/.local/bin"

say() { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

need() {
	command -v "$1" >/dev/null 2>&1 || die "this installer needs '$1' and could not find it"
}

# --- what are we on ----------------------------------------------------------

detect_platform() {
	os="$(uname -s)"
	arch="$(uname -m)"

	case "${os}" in
		Linux) os="linux" ;;
		Darwin) os="darwin" ;;
		*) die "unsupported operating system: ${os}. Install from source instead." ;;
	esac

	case "${arch}" in
		x86_64 | amd64) arch="amd64" ;;
		arm64 | aarch64) arch="arm64" ;;
		*) die "unsupported architecture: ${arch}. Install from source instead." ;;
	esac

	printf '%s-%s\n' "${os}" "${arch}"
}

# --- where does it go --------------------------------------------------------

# Returns the first directory on PATH that this user can write to. Empty when
# there is none, which is the case the fallback below exists for and which is
# ordinary on a managed workstation.
writable_path_dir() {
	saved_ifs="${IFS}"
	IFS=:
	for candidate in ${PATH}; do
		[ -n "${candidate}" ] || continue
		case "${candidate}" in
			/usr/* | /bin | /sbin) continue ;;  # system-owned; would need root
		esac
		if [ -d "${candidate}" ] && [ -w "${candidate}" ]; then
			IFS="${saved_ifs}"
			printf '%s\n' "${candidate}"
			return 0
		fi
	done
	IFS="${saved_ifs}"
	return 0
}

on_path() {
	saved_ifs="${IFS}"
	IFS=:
	for candidate in ${PATH}; do
		if [ "${candidate}" = "$1" ]; then
			IFS="${saved_ifs}"
			return 0
		fi
	done
	IFS="${saved_ifs}"
	return 1
}

# The exact line to add, for the shell that is actually running. A generic
# "add it to your profile" is an instruction somebody has to go and translate.
path_instruction() {
	target="$1"
	shell_name="$(basename "${SHELL:-/bin/sh}")"
	case "${shell_name}" in
		zsh) profile="${ZDOTDIR:-${HOME}}/.zshrc" ;;
		bash) profile="${HOME}/.bashrc" ;;
		fish)
			say "  fish_add_path ${target}"
			return 0
			;;
		*) profile="${HOME}/.profile" ;;
	esac
	say "  echo 'export PATH=\"${target}:\$PATH\"' >> ${profile}"
	say "  exec ${shell_name}"
}

# --- integrity ---------------------------------------------------------------

sha256_of() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | cut -d' ' -f1
	elif command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$1" | cut -d' ' -f1
	else
		die "no sha256 tool found. Install coreutils or perl, or install from source."
	fi
}

verify() {
	archive="$1"
	expected_file="$2"
	name="$(basename "${archive}")"

	expected="$(grep -F "  ${name}" "${expected_file}" 2>/dev/null | cut -d' ' -f1 || true)"
	[ -n "${expected}" ] || die "no published checksum for ${name}. Refusing to install."

	actual="$(sha256_of "${archive}")"
	if [ "${actual}" != "${expected}" ]; then
		die "checksum mismatch for ${name}.
  expected ${expected}
  got      ${actual}
Refusing to install. Something between the release and this machine changed it."
	fi
	say "verified ${name}"
}

# --- install -----------------------------------------------------------------

main() {
	need uname
	need mkdir
	need tar

	if command -v curl >/dev/null 2>&1; then
		fetch() { curl -fsSL "$1" -o "$2"; }
	elif command -v wget >/dev/null 2>&1; then
		fetch() { wget -qO "$2" "$1"; }
	else
		die "this installer needs curl or wget and could not find either"
	fi

	platform="$(detect_platform)"
	archive_name="${APP_NAME}-${VERSION}-${platform}.tar.gz"
	base="${RELEASE_BASE}/${VERSION}"

	target="$(writable_path_dir)"
	fallback=0
	if [ -z "${target}" ]; then
		target="${FALLBACK_DIR}"
		fallback=1
	fi

	mkdir -p "${target}" || die "could not create ${target}"
	[ -w "${target}" ] || die "cannot write to ${target}. This installer never uses sudo."

	work="$(mktemp -d)" || die "could not create a temporary directory"
	# Cleaned up whatever happens, including a failed verification — a rejected
	# archive left in /tmp is one somebody eventually runs by hand.
	trap 'rm -rf "${work}"' EXIT INT TERM

	say "downloading ${archive_name}"
	fetch "${base}/${archive_name}" "${work}/${archive_name}" ||
		die "could not download ${base}/${archive_name}"
	fetch "${base}/SHA256SUMS" "${work}/SHA256SUMS" ||
		die "could not download the checksums. Refusing to install unverified."

	verify "${work}/${archive_name}" "${work}/SHA256SUMS"

	tar -xzf "${work}/${archive_name}" -C "${work}" || die "could not unpack ${archive_name}"
	[ -f "${work}/${APP_NAME}" ] || die "the archive did not contain ${APP_NAME}"

	mv "${work}/${APP_NAME}" "${target}/${APP_NAME}"
	chmod +x "${target}/${APP_NAME}"
	say "installed ${target}/${APP_NAME}"

	if [ "${fallback}" -eq 1 ] || ! on_path "${target}"; then
		say ""
		warn "${target} is not on your PATH. Add it:"
		path_instruction "${target}"
		say ""
	fi

	say ""
	say "Next: ${APP_NAME} onboard"
}

main "$@"

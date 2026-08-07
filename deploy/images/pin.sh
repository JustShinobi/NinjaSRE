#!/bin/sh
# Resolve every base image in base-images.env to a digest, and rewrite the file.
#
# A tag is a pointer somebody else can move. A digest is the image. Pinning them
# is what makes a build in six months produce the bytes it produced today —
# which matters most for the deployment nobody is watching, where a base image
# that quietly changed is discovered by a failing health check.
#
# This is a script rather than a set of digests committed to the repository,
# because a digest resolves against a registry: an operator mirroring images
# into their own has different digests for the same tags, and a digest written
# by hand is one nobody verified. Run this against the registry you actually
# pull from, and commit what it produces if you keep a fork.
#
# Usage:
#     sh deploy/images/pin.sh              # rewrite base-images.env in place
#     sh deploy/images/pin.sh --check      # fail if anything is unpinned

set -eu

FILE="$(dirname "$0")/base-images.env"
CHECK=""
[ "${1:-}" = "--check" ] && CHECK="yes"

resolve() {
    reference="$1"
    # Already pinned: keep it. Re-resolving a digest would be a way to
    # accidentally follow a tag that has moved since somebody pinned it.
    case "${reference}" in
        *@sha256:*) echo "${reference}"; return ;;
    esac
    if [ -n "${CHECK}" ]; then
        echo "unpinned: ${reference}" >&2
        return 1
    fi
    digest="$(docker buildx imagetools inspect --format '{{.Manifest.Digest}}' "${reference}")"
    echo "${reference}@${digest}"
}

STATUS=0
OUTPUT="$(mktemp)"
trap 'rm -f "${OUTPUT}"' EXIT

while IFS= read -r line; do
    case "${line}" in
        ''|\#*)
            printf '%s\n' "${line}" >> "${OUTPUT}"
            continue
            ;;
    esac
    name="${line%%=*}"
    reference="${line#*=}"
    if pinned="$(resolve "${reference}")"; then
        printf '%s=%s\n' "${name}" "${pinned}" >> "${OUTPUT}"
    else
        STATUS=1
        printf '%s\n' "${line}" >> "${OUTPUT}"
    fi
done < "${FILE}"

if [ -z "${CHECK}" ] && [ "${STATUS}" -eq 0 ]; then
    cp "${OUTPUT}" "${FILE}"
    echo "Pinned every base image in ${FILE}." >&2
fi

if [ "${STATUS}" -ne 0 ]; then
    echo "Some base images are not pinned to a digest. Run this without --check." >&2
fi

exit "${STATUS}"

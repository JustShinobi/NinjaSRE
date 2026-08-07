#!/bin/sh
# Export every image this deployment runs as one archive, for an air-gapped
# install (FR-023).
#
# One archive rather than four, because the thing carrying it is usually a USB
# stick and a person, and four files is three chances to forget one. `docker
# save` deduplicates shared layers across the images in a single invocation,
# so the combined archive is smaller than the four separate ones anyway.
#
# The local model is not in here and cannot be: it is gigabytes, it is the
# operator's choice, and Ollama and vLLM both have their own distribution
# story. `docs/deployment.md` says which one to pull and where to put it.
#
# On the far side:
#     docker load --input ninjasre-images.tar.gz
#     docker compose up -d          # nothing is pulled; everything is local
#
# Usage:
#     sh deploy/images/bundle.sh [OUTPUT.tar.gz]

set -eu

OUTPUT="${1:-ninjasre-images.tar.gz}"
TAG="${NINJASRE_IMAGE_TAG:-local}"

IMAGES="ninjasre/app:${TAG} ninjasre/console:${TAG} ninjasre/proxy:${TAG} ninjasre/postgres:${TAG}"

echo "Building the four images at tag ${TAG}..." >&2
docker build -f deploy/images/app.Dockerfile      -t "ninjasre/app:${TAG}"      .
docker build -f deploy/images/console.Dockerfile  -t "ninjasre/console:${TAG}"  .
docker build -f deploy/images/proxy.Dockerfile    -t "ninjasre/proxy:${TAG}"    .
docker build -f deploy/images/postgres.Dockerfile -t "ninjasre/postgres:${TAG}" .

echo "Saving them into ${OUTPUT}..." >&2
# shellcheck disable=SC2086 -- IMAGES is a deliberate word list
docker save ${IMAGES} | gzip > "${OUTPUT}"

echo "Wrote ${OUTPUT}" >&2
echo "On the air-gapped host: docker load --input $(basename "${OUTPUT}")" >&2
echo "${OUTPUT}"

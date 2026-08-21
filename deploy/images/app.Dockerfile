# The application: REST and SSE surface, webhooks, the investigation runtime.
#
# Multi-stage, and the split is not cosmetic. The build stage installs a
# compiler toolchain and a package manager; the runtime stage gets a virtual
# environment and nothing that could compile or fetch anything. An image that
# can build is an image an attacker can build in.
#
# Non-root, with an explicit numeric UID. A Kubernetes `runAsNonRoot` check
# reads the *number* — a named user resolves at runtime and a pod is rejected
# for a user the kubelet cannot resolve, which is a confusing way to find out.

# syntax=docker/dockerfile:1
ARG BASE_PYTHON=python:3.14.7-slim-trixie

FROM ${BASE_PYTHON} AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /src

# The lock file and the manifest first, so a source-only change does not
# reinstall the dependency tree.
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY capabilities ./capabilities
COPY config ./config
COPY core ./core
COPY gateway ./gateway
COPY integrations ./integrations
COPY platform ./platform
COPY surfaces ./surfaces

# Into a virtual environment rather than the system interpreter, so the runtime
# stage copies one directory and inherits nothing else the build needed.
#
# With the provider extras, not bare. A bare install leaves every provider
# adapter unimportable, and nothing notices until a model is actually invoked —
# health is green, the credential verifies, the console renders, and the first
# investigation fails with a message about a missing extra.
#
# Every provider rather than one: which provider an operator configures is not
# knowable at build time, and an image that works for one and not another is an
# image whose behaviour depends on a setting made long after it was built.
RUN python -m venv /opt/ninjasre \
    && /opt/ninjasre/bin/pip install --no-cache-dir ".[all-providers]" \
    && ln -s "$(/opt/ninjasre/bin/python -c 'import site; print(site.getsitepackages()[0])')" \
        /opt/ninjasre/site-packages

FROM ${BASE_PYTHON} AS runtime

LABEL org.opencontainers.image.title="NinjaSRE" \
      org.opencontainers.image.description="Self-hosted AI SRE platform" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/ninjasre/ninjasre"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/ninjasre/bin:${PATH}" \
    PYTHONPATH="/opt/ninjasre/site-packages"

# 10001 rather than the distribution's first free UID: high enough not to
# collide with a host user if the filesystem is ever shared, and fixed so a
# volume written by one release is readable by the next.
RUN groupadd --gid 10001 ninjasre \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ninjasre

COPY --from=build --chown=root:root /opt/ninjasre /opt/ninjasre

# The catalogue is built into the image (Article IX). A deployment that fetched
# its capability list at runtime would be one whose behaviour depends on a
# network it was told it does not have.
COPY --from=build --chown=root:root /src/capabilities /opt/ninjasre/share/capabilities

USER 10001:10001
WORKDIR /var/lib/ninjasre

EXPOSE 8420

# Liveness, which asks only whether the process should keep running. Readiness
# is the gate that decides whether it is sent traffic, and it is a separate
# endpoint because the two answers differ during a migration.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8420/health/live', timeout=4).status == 200 else 1)"]

# The boot sequence and the server, on one event loop. See gateway/http/serve.py
# for why this is a module rather than a pointer at an ASGI factory.
ENTRYPOINT ["python", "-m", "gateway.http.serve"]
CMD ["--host", "0.0.0.0", "--port", "8420"]

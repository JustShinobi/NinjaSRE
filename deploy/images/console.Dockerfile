# The web console's backend-for-frontend.
#
# The same wheel as the application, started at a different entry point. One
# image would have been fewer bytes; two is what lets an operator give the
# console a different replica count, a different resource budget, and a
# different network position from the thing that holds credentials — which is
# the reason the standard profile has four containers rather than three.

# syntax=docker/dockerfile:1
ARG BASE_PYTHON=python:3.12.11-slim-bookworm

FROM ${BASE_PYTHON} AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /src

COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY capabilities ./capabilities
COPY config ./config
COPY core ./core
COPY gateway ./gateway
COPY integrations ./integrations
COPY platform ./platform
COPY surfaces ./surfaces

RUN python -m venv /opt/ninjasre \
    && /opt/ninjasre/bin/pip install --no-cache-dir .

FROM ${BASE_PYTHON} AS runtime

LABEL org.opencontainers.image.title="NinjaSRE console" \
      org.opencontainers.image.description="Web console for NinjaSRE" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/ninjasre/bin:${PATH}"

RUN groupadd --gid 10001 ninjasre \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ninjasre

COPY --from=build --chown=root:root /opt/ninjasre /opt/ninjasre

USER 10001:10001
WORKDIR /var/lib/ninjasre

EXPOSE 8421

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8421/health/live', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "gateway.http.serve"]
CMD ["--host", "0.0.0.0", "--port", "8421"]

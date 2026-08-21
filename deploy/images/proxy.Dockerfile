# The credential proxy. The only process in a NinjaSRE deployment that holds a
# secret, and the reason every other one can be reasoned about without asking
# where the credentials are.
#
# Nothing here is different from the application image except the entry point
# and what the image is *for*. That is deliberate: separating it buys a
# separate network position, a separate resource budget, and a container an
# operator can point their own scanner at and say "this is the one that
# matters" — none of which is available when the trust boundary is a module in
# a bigger process.

# syntax=docker/dockerfile:1
ARG BASE_PYTHON=python:3.14.7-slim-trixie

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

LABEL org.opencontainers.image.title="NinjaSRE credential proxy" \
      org.opencontainers.image.description="Injects credentials at the network edge" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/ninjasre/bin:${PATH}"

RUN groupadd --gid 10001 ninjasre \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ninjasre

COPY --from=build --chown=root:root /opt/ninjasre /opt/ninjasre

USER 10001:10001
WORKDIR /var/lib/ninjasre

EXPOSE 8422

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8422/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "platform.credentials.proxy"]
CMD ["--host", "0.0.0.0", "--port", "8422"]

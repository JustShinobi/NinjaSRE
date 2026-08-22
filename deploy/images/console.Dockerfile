# The web console's backend-for-frontend.
#
# The same wheel as the application, started at a different entry point. One
# image would have been fewer bytes; two is what lets an operator give the
# console a different replica count, a different resource budget, and a
# different network position from the thing that holds credentials — which is
# the reason the standard profile has four containers rather than three.

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
    && /opt/ninjasre/bin/pip install --no-cache-dir ".[all-providers]" \
    && ln -s "$(/opt/ninjasre/bin/python -c 'import site; print(site.getsitepackages()[0])')" \
        /opt/ninjasre/site-packages \
    # `pip` installed this environment and has no part in running it. It is also
    # the only thing in the image carrying a vendored `msgpack` and a bundled
    # `setuptools`, which is where two of this image's reported vulnerabilities
    # came from — not from anything this project depends on. Removing the
    # installer from the runtime environment answers both, and leaves nothing
    # behind that could install anything into a running container.
    && rm -rf /opt/ninjasre/lib/python*/site-packages/pip \
        /opt/ninjasre/lib/python*/site-packages/pip-*.dist-info \
        /opt/ninjasre/bin/pip /opt/ninjasre/bin/pip3 /opt/ninjasre/bin/pip3.*

FROM ${BASE_PYTHON} AS runtime

LABEL org.opencontainers.image.title="NinjaSRE console" \
      org.opencontainers.image.description="Web console for NinjaSRE" \
      org.opencontainers.image.licenses="Apache-2.0"


# The base image's Debian packages, brought to the security updates published
# since it was built. Every one of this image's remaining reported
# vulnerabilities came from a single source package, `util-linux`, fixed in
# trixie and not yet in a republished base — so pinning a newer base tag does
# nothing and this is what closes them.
#
# `--only-upgrade`, so this installs nothing new: it is a security refresh of
# what the base already carries, not a way for packages to arrive unnoticed.
# `ensurepip`'s bundled wheel goes too, for the same reason `pip` does above.
RUN apt-get update \
    && apt-get install --no-install-recommends --only-upgrade --yes \
        bsdutils libblkid1 liblastlog2-2 libmount1 libsmartcols1 libuuid1 \
        login mount util-linux \
    && rm -rf /var/lib/apt/lists/* /usr/local/lib/python*/ensurepip/_bundled \
        /usr/local/lib/python*/site-packages/pip /usr/local/lib/python*/site-packages/pip-*.dist-info \
        /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/ninjasre/bin:${PATH}" \
    PYTHONPATH="/opt/ninjasre/site-packages"

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

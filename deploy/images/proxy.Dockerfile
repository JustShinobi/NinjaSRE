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

# No provider extras: the proxy injects credentials at the network edge and
# never invokes a model, so a vendor SDK here would be weight with no purpose.
#
# The symlink is not cosmetic. `platform/` shadows the standard library module
# of that name and only wins it when its own directory leads the path, so the
# runtime stage puts `site-packages` on `PYTHONPATH` explicitly and this is the
# stable name it points at.
RUN python -m venv /opt/ninjasre \
    && /opt/ninjasre/bin/pip install --no-cache-dir . \
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

LABEL org.opencontainers.image.title="NinjaSRE credential proxy" \
      org.opencontainers.image.description="Injects credentials at the network edge" \
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

EXPOSE 8422

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8422/internal/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "gateway.proxy"]
CMD ["--host", "0.0.0.0", "--port", "8422"]

# The console a browser loads.
#
# The other three images are the same Python wheel started at different entry
# points. This one is not: the console is a Next.js application, and what a
# person opens is the server that renders it. Without this image the deployment
# has an ingress pointing a browser at a gateway, which answers every request
# for `/` with a JSON 404 — correctly, because a gateway is not a console.
#
# It talks to the gateway on 8421 from the server side, never from the browser.
# That is what keeps the API's origin out of a page's reach and lets the
# console container hold a credential a browser never sees.

# syntax=docker/dockerfile:1
ARG BASE_NODE=node:24.19.0-trixie-slim

FROM ${BASE_NODE} AS build

WORKDIR /src/console

# The manifest and the lockfile first, so a change to a component does not
# reinstall the dependency tree. `--frozen-lockfile` because a build that
# resolved its own versions would ship a console nobody tested.
# `pnpm-workspace.yaml` alongside them, and not as an afterthought: it carries
# the allowlist of dependencies permitted to run an install script, and pnpm
# refuses the whole install when one it does not recognise is ignored. Leaving
# it out fails the build with a message about `unrs-resolver` that says nothing
# about a missing file.
COPY console/package.json console/pnpm-lock.yaml console/pnpm-workspace.yaml ./
# `CI` because pnpm asks for a TTY before removing a modules directory it does
# not recognise, and a build has none. It should never have one to remove — the
# context excludes `node_modules` — but a build that hangs on a prompt nobody
# can answer is a worse failure than the one it is guarding against.
ENV CI=true

RUN corepack enable \
    && corepack prepare --activate \
    && pnpm install --frozen-lockfile

COPY console ./

# `next build` leaves the static assets where a CDN would have collected them;
# `prepare-standalone` copies them in, which is what makes the output a
# directory this deployment can run with nothing else installed.
RUN pnpm run build

FROM ${BASE_NODE} AS runtime

LABEL org.opencontainers.image.title="NinjaSRE console" \
      org.opencontainers.image.description="The web console a browser loads" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/ninjasre/ninjasre"

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=8425

# The security updates published since the base was built, and the package
# manager that installed nothing here. `npm` and `corepack` ship with the image
# and have no part in running it — the standalone output carries its own module
# graph — and leaving an installer in a running container is leaving a way to
# put something new into one.
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
        /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

RUN groupadd --gid 10001 ninjasre \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ninjasre

COPY --from=build --chown=root:root /src/console/.next/standalone /opt/ninjasre-console

USER 10001:10001
WORKDIR /opt/ninjasre-console

EXPOSE 8425

# The console's own root, not a health route it does not serve. Next.js answers
# `/` once the server is listening, and a check that asked for a path this
# application has never had would report unhealthy for the container's whole
# life while it answered every real request.
#
# Anything under 400 counts, and the redirect is not followed. A visitor with no
# session is sent to `/sign-in`, so `/` answers 307 — which `response.ok` calls
# a failure. A check written that way would have reported this container
# unhealthy from its first second, for doing the right thing.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:8425/',{redirect:'manual'}).then(r=>process.exit(r.status<400?0:1)).catch(()=>process.exit(1))"]

ENTRYPOINT ["node", "server.js"]

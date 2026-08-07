# NinjaSRE documentation

A self-hosted AI SRE platform. It investigates production incidents, produces
evidence-backed root causes, learns from every run, and measures whether that
learning helps.

Nothing here talks to us. There is no NinjaSRE account, no telemetry, and no
hosted control plane — this site builds and serves offline, from the same
repository the software comes from.

## Start here

- **[Quickstart](quickstart/index.md)** — from nothing to a finished
  investigation, using only that page.

## Running it

- **[Deployment](deployment/index.md)** — the three profiles, upgrading,
  backups, key rotation, and running with no internet.
- **[Configuration](configuration/index.md)** — every setting, generated from
  the catalogue the deployment actually reads.
- **[Security](security/index.md)** — the five controls, each named with the
  threat it addresses, and what is deliberately not defended against.

## What it can do

- **[Capabilities](capabilities/index.md)** — everything the agent can call, and
  the side-effect level each one is gated at. Generated from the declarations the
  approval gate reads.
- **[Integrations](integrations/index.md)** — every vendor, its credential, and
  the permissions verification probes. Generated from the catalogue.

## Whether it works

- **[Evaluation](evaluation/index.md)** — the exact commands to reproduce every
  published number, and how to disagree with one.

## Changing it

- **[Contributing](contributing/index.md)** — the tier table, where things go,
  the conventions, and the seven artefacts every integration ships.

## Which pages are generated

Three sections — capabilities, integrations, and configuration — are produced
from the code by `tools/generate_docs.py`, and a drift check in `make verify`
fails if they were not regenerated after a change. They describe what the code
*is*, and a hand-written description of that is wrong within two releases.

Everything else is authored, because it describes decisions and threats, which
is what a person is for. Every code example in an authored page is extracted and
checked, so a command that stops working fails the build rather than an operator.

## Reading this offline

```sh
make docs-build     # renders the whole site into docs/site/build
make docs-serve     # builds it and serves it on localhost, with no network access
```

The build has no external asset, no font, no script, and no analytics. It is a
directory of HTML you can copy onto a machine with no internet and open.

## Translations

English is the normative source. `docs/site/i18n/` holds the structure a
community translation goes in, and a translated page that has drifted from its
source is reported rather than silently served.

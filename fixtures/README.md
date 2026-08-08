# The mock data plane

A deterministic, anonymised dataset describing a deployment, and a mock API that
serves it on the same paths the gateway serves. The console can be built,
reviewed and regression-tested against it with no backend, no cluster, no
database and no model.

```bash
python -m tools.mockplane serve                    # the dataset over HTTP
python -m tools.mockplane console                  # the mock and the console in front of it
python -m tools.mockplane console --scenario empty # any declared scenario
python -m tools.mockplane verify                   # every check, on demand
```

Programmatically, for a test:

```python
from tools.mockplane.server import build_mock

mock = build_mock("populated")
mock.answer("GET", "/v1/runs")
```

## What is here

| Path | What it holds |
|---|---|
| `manifest.json` | Every declared scenario, and the per-endpoint overrides that make one misbehave. |
| `contract/openapi.json` | The gateway's own API document, generated from the routes. Every fixture validates against it, and a route change that invalidates one fails the build naming the endpoint and the field. |
| `contract/projected.json` | The response shapes of the endpoints nothing serves yet. Each path is deleted from this file by the change that makes the gateway serve it. |
| `scenarios/<name>/<endpoint>.json` | One endpoint's answers under one scenario. |

## The scenarios

| Name | What it is for |
|---|---|
| `populated` | A full deployment mid-operation. The default. |
| `empty` | Nothing in it. The only way an empty state gets reviewed at all. |
| `first-run` | Configured and not finished, so the setup checklist renders. |
| `degraded` | Endpoints slow, refused, 500, 403, 404 and truncated, so panel-level error handling is exercised. Holds no files: it is `populated` plus a declaration. |
| `incident-live` | A run in flight, streaming. |
| `restricted` | The same deployment seen by a viewer. |
| `scale` | Ten thousand runs, events and resources and a five-hundred-node configuration tree. Generated from a fixed seed rather than committed. |

Adding a scenario is a manifest entry and, at most, the files that differ from
the scenario it derives from. Nothing in the console changes.

## What the dataset is, and is not

**It is derived from a real deployment, not invented.** Invented fixtures encode
somebody's idea of what infrastructure looks like, which is tidy, evenly
distributed and mostly healthy. What is here is none of those: eighty-two
containers against two virtual machines, one node carrying almost everything
that runs, a guest at 99.6% of its own volume while the datastore under it reads
84%, a backup job that exists and is switched off, nine failed units on one host,
two datastores answering `unknown`, and a quorum with no margin at all. Those are
the cases a console has to survive and the ones nobody thinks to invent, so
`tests/contract/fixtures/` asserts each of them is still here.

**Nothing in it is real.** Every name, address, domain and principal is a stable
pseudonym; addresses come from the ranges the standards reserve for
documentation and the domain is under `.invalid`, which can never resolve. The
mapping is derived under a key that is not in this repository. An adversarial
scan runs in the gate over everything committed here, and the operator's list of
actual values — held outside the repository — is a second net:

```bash
python -m tools.mockplane verify --identifiers ~/real-values.txt
```

**Timestamps are shifted, not frozen.** Every one moved by a single offset onto a
fixed instant, so two runs of the pipeline are byte-identical and a visual diff
compares code against code — while "four minutes ago" and "two days ago" stay
four minutes and two days apart.

**It is not a substitute for the end-to-end suite.** This is development and test
infrastructure. Nothing here runs in a deployment.

## Regenerating it

```bash
python -m tools.mockplane contract   # the API document, from the routes
python -m tools.mockplane build      # the scenario files
```

Both are checked: a committed file that differs from what the builder produces
fails the suite, so the two cannot drift.

Refreshing from a live deployment needs one, and the capture is read-only:

```bash
python -m tools.mockplane capture
```

It records what the gateway already serves, reads the cluster directly for what
it does not, and reports every endpoint it could not reach, per source. Raw
captures are written outside the repository and are never committed — they carry
hostnames, guest configuration and, potentially, cloud-init secrets.

Asking the cluster a question nobody anticipated is the same channel:

```bash
python -m tools.mockplane ask --node node01 systemctl list-units --failed --no-legend --plain --no-pager
```

Every read comes from a declared allowlist in
`tools/mockplane/read_only_commands.json`. A command outside it fails rather than
running, and extending the list is a change to that file — which is a diff
somebody reviews.

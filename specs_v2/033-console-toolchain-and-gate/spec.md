# Feature 033 — Console Toolchain and Quality Gate

- **Wave:** 9 — Console rework
- **Branch:** `feat/033-console-toolchain-and-gate`
- **Status:** Draft
- **Depends on:** none — this and 032 are the two foundations the rest of the wave stands on

## Summary

The decision the first wave declined, made explicitly: a TypeScript front end
enters the repository, and `make verify` grows a second half so that it is not
invisible to the gate that defines "done".

This must land first. `../specs/021-web-console/deviations.md` records that the
console was built in Python largely because a TypeScript surface would have gone
unlinted, untyped, untested and unchecked while `make verify` still went green —
"satisfied vacuously" is the phrase. That reasoning was correct. The only
honest way to overturn the conclusion is to remove the premise before writing a
line of the new console, which is what this feature does.

It also decides what happens to `surfaces/console/`: retired, in one commit, when
the new console reaches parity — not left in place as a second implementation of
every screen.

## User scenarios

### Primary story

A contributor clones the repository and runs `make verify`. It installs what it
needs, lints and type-checks the Python and the TypeScript, runs both suites,
checks the import contracts, runs the browser tests against a real gateway, and
compares the console against its visual baselines. One command, one verdict, no
part of the system outside it.

A contributor opens a pull request that changes a colour token. CI shows them the
three screens that changed and asks them to accept or reject the new baselines.

### Acceptance scenarios

1. **Given** a clean checkout, **when** `make verify` runs, **then** the console
   is linted, type-checked, unit-tested, built, and end-to-end tested, and a
   failure in any of those fails the command.
2. **Given** a type error in a console source file, **when** `make verify` runs,
   **then** it fails and names the file and line.
3. **Given** a console change that alters a rendered screen, **when** CI runs,
   **then** the visual difference is reported with an image, and the run fails
   until a baseline is accepted.
4. **Given** the gateway's OpenAPI document changing incompatibly, **when** the
   console builds, **then** the build fails rather than shipping a client that
   calls an endpoint that no longer exists.
5. **Given** a contributor with no Node installed, **when** they run
   `make verify`, **then** the toolchain is provisioned reproducibly, pinned, and
   the same version CI uses.
6. **Given** the three platforms CI covers, **when** the workflow runs, **then**
   the console gate runs on each and passes.
7. **Given** the new console at parity, **when** `surfaces/console/` is removed,
   **then** nothing else in the repository references it and the suite still
   passes.
8. **Given** a production build, **when** it is served, **then** it fetches
   nothing from a third-party host.

### Edge cases

- A lockfile out of date with the manifest.
- A browser binary missing on a CI runner.
- Visual baselines captured on a different platform than the one comparing them.
- A generated API client checked in stale.
- An air-gapped build with no registry access.
- A contributor running only the Python half during a quick iteration.

## Requirements

### Functional

**Toolchain**

- **FR-001** The console MUST live in one directory with its own manifest and a
  committed lockfile.
- **FR-002** The package manager, the Node version and the browser binaries MUST
  be pinned, and the pinned versions MUST be what CI uses.
- **FR-003** The toolchain MUST be provisionable by a single make target that is
  idempotent and does not require a pre-existing Node installation.
- **FR-004** A stale lockfile MUST fail the build rather than being silently
  updated.

**Gate**

- **FR-005** `make verify` MUST run, for the console: format check, lint, type
  check, unit tests, production build, end-to-end tests, and visual regression.
- **FR-006** Each of those MUST also be runnable individually, so a contributor
  iterating on one need not run all.
- **FR-007** A failure in any console check MUST fail `make verify` with a message
  naming what failed and where.
- **FR-008** The console's test suite MUST report coverage against a declared
  threshold, enforced.
- **FR-009** The gate MUST run on all three platforms the existing CI workflow
  covers.

**API client generation**

- **FR-010** The API client MUST be generated from the gateway's OpenAPI document
  and committed.
- **FR-011** The build MUST fail when the committed client differs from a fresh
  generation against the current document.
- **FR-012** The generation MUST be runnable offline from a committed copy of the
  document, so an air-gapped build works.

**End-to-end and visual**

- **FR-013** End-to-end tests MUST run against a real gateway with a real
  database, provisioned by the same compose definition the deployment uses.
- **FR-014** Visual baselines MUST be captured in one pinned container image and
  compared only against captures from that same image.
- **FR-015** A visual difference MUST be reported as an image artefact and MUST
  fail the run until a baseline is explicitly accepted.
- **FR-016** Accepting baselines MUST be a reviewable change, not a flag.

**Retirement**

- **FR-017** `surfaces/console/` MUST be removed once the new console reaches
  parity on every screen the first wave shipped.
- **FR-018** Its removal MUST be one change: the package, its tests, its entry
  point, its Docker image, its Helm template, its constants, and every reference.
- **FR-019** The console's deployment artefacts MUST be updated to serve the new
  build, and the deployment MUST still be a single-host compose bring-up.
- **FR-020** Nothing in the Python tree may import from the console after
  retirement, enforced by an import contract.

**Distribution**

- **FR-021** The production build MUST bundle every asset, including fonts and
  icons. No runtime request may leave the deployment.
- **FR-022** The build output MUST be servable behind the same reverse proxy the
  deployment already runs, on a path the operator can configure.

### Non-functional

- **NFR-001** A cold `make verify` MUST complete within a declared budget on CI;
  a warm one within a much smaller one.
- **NFR-002** Console checks MUST run in parallel with the Python ones where they
  do not contend.
- **NFR-003** The end-to-end suite MUST be deterministic — no test may depend on
  wall-clock timing or network latency to a third party.
- **NFR-004** The provisioning step MUST be cacheable in CI, so a run that changes
  no dependency does not reinstall.

## Success criteria

- **SC-001** `make verify` on a clean checkout runs and passes both halves.
- **SC-002** A seeded type error, lint violation, failing unit test, failing
  end-to-end test and visual difference each fail `make verify`, individually.
- **SC-003** A stale committed API client fails the build.
- **SC-004** The workflow passes on all three platforms.
- **SC-005** After retirement, no reference to `surfaces/console/` remains and an
  import contract enforces it.
- **SC-006** A production build serves with no third-party request, asserted by a
  network audit in the end-to-end suite.
- **SC-007** Cold and warm `make verify` budgets hold.

## Out of scope

- The console's content — features 034 through 035.
- Changing the Python toolchain.
- Publishing the console as a separate package.

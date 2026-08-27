# Feature 042 — First Run, Seeding and Demo Mode

- **Wave:** 10 — Autonomous operation
- **Branch:** `feat/042-first-run-and-demo`
- **Status:** Draft
- **Depends on:** 030, 032

## Summary

The path from `docker compose up` to a console showing something worth looking
at, without the operator having to know anything about the system first.

This feature exists because of a specific observation from the first live run.
The stack came up. The gateway served fifty-one endpoints. The console rendered a
sign-in. The bootstrap admin token printed into the environment was **rejected**
by the running gateway, so there was no way past the sign-in at all; and had
there been, every list behind it would have been empty. A platform that works
perfectly and cannot be entered is, from where the operator is standing,
indistinguishable from one that does not work.

Three things, then: a bootstrap that provably works, a first-run experience that
takes an operator from nothing to a completed investigation, and a demo mode that
makes the console show a real system's worth of data without a real system.

## User scenarios

### Primary story

Someone clones the repository and runs one command. The stack comes up. The
terminal prints a sign-in URL and a token, and says how long the token is good
for. They open the URL, paste the token, and are in.

The console does not show them eight empty tables. It shows a setup checklist:
connect a model provider, connect an infrastructure source, run your first
investigation. Each step verifies itself and says what is wrong when it fails —
not "connection error" but "the model endpoint answered, but not with a model
that supports tool calling; here are the ones it offers that do".

Fifteen minutes later they have watched a real investigation run against their
own infrastructure.

Alternatively they run the same command with a demo flag, and the console comes
up populated: an estate, incidents, completed investigations with full
transcripts, episodes, strategies, a topology. Nothing is connected to anything
real, everything is labelled as demonstration, and they can see the entire
product in two minutes.

### Acceptance scenarios

1. **Given** a clean machine with the prerequisites, **when** the bring-up command
   runs, **then** the stack starts, migrations apply, and a working sign-in
   credential is printed with its expiry.
2. **Given** the printed credential, **when** it is used to sign in, **then** it
   is accepted. A test MUST assert this against a freshly bootstrapped
   deployment.
3. **Given** a bootstrap credential, **when** it is first used, **then** the
   operator is required to establish a durable credential, and the bootstrap one
   expires.
4. **Given** a deployment with nothing configured, **when** the console is opened,
   **then** a setup checklist is shown with the state of each step.
5. **Given** any setup step, **when** it is verified, **then** the result names
   the specific problem and the specific next action, never a bare failure.
6. **Given** a model provider configured, **when** it is verified, **then** the
   verification proves tool calling and structured output work, not merely that
   the endpoint answers.
7. **Given** the setup complete, **when** the operator runs the guided first
   investigation, **then** it completes and its transcript is readable.
8. **Given** demo mode, **when** the stack comes up, **then** the console is
   populated with a coherent estate, incidents, runs, episodes, strategies and
   topology, all labelled as demonstration data.
9. **Given** demo mode, **when** anything would call a real provider, **then** it
   does not; every external call is served from fixtures.
10. **Given** demo mode, **when** it is disabled, **then** the demonstration data
    is removable in one action and nothing of it remains.
11. **Given** a deployment that is misconfigured, **when** the self-check runs,
    **then** it reports every problem it can find in one pass, ordered by what
    blocks the most.
12. **Given** any failure during bring-up, **when** it happens, **then** the
    message says what failed, why, and what to do — and the same message is
    reachable later from the console and the CLI.

### Edge cases

- A port already in use on the host.
- A database that exists from a previous version.
- A model endpoint that is reachable but has no model pulled.
- A machine with too little memory for the configured model.
- Bring-up run twice.
- Demo mode enabled on a deployment that already has real data.
- A bootstrap credential leaked into a log.
- An operator who closes the terminal before reading the token.

## Requirements

### Functional

**Bootstrap**

- **FR-001** Bring-up MUST produce a credential that signs in successfully, and
  this MUST be asserted end-to-end against a freshly bootstrapped deployment.
- **FR-002** The credential MUST be printed with its expiry and MUST be
  retrievable again from the host without restarting anything.
- **FR-003** The bootstrap credential MUST be single-purpose and short-lived: it
  establishes a durable credential and then expires.
- **FR-004** The bootstrap credential MUST NOT appear in any log, any audit
  export, or any error message.
- **FR-005** Bring-up MUST be idempotent. Running it twice MUST NOT reset, wipe,
  or duplicate anything.
- **FR-006** Migrations MUST apply automatically and MUST refuse rather than
  guess when the schema is from an incompatible version.

**Self-check**

- **FR-007** A self-check MUST verify, at minimum: database reachability and
  schema version, the credential proxy, the model provider including tool calling
  and structured output, each configured integration, the scheduler, the observer,
  disk space, and clock skew.
- **FR-008** The self-check MUST report every problem it finds in one pass,
  ordered by how much each blocks.
- **FR-009** Every finding MUST name the specific problem and the specific next
  action. A finding that says only that something failed MUST NOT be shippable —
  a test MUST assert every finding has both.
- **FR-010** The self-check MUST be runnable from the CLI, from the console, and
  automatically during bring-up.

**Setup**

- **FR-011** The console MUST present a setup checklist when the deployment is
  incomplete, with the state of each step and the next action.
- **FR-012** Each step MUST verify itself against the real dependency, not against
  the presence of configuration.
- **FR-013** The checklist MUST disappear on completion and MUST be reachable
  afterwards.
- **FR-014** A guided first investigation MUST be offered, MUST run against
  whatever the operator connected, and MUST produce a readable transcript.

**Demo mode**

- **FR-015** Demo mode MUST populate **feature 032's dataset** — the anonymised
  capture of a real deployment — loaded into the real database. It MUST NOT
  define a second fictional deployment. The scenario covers: an estate with several
  kinds of resource, a topology among them, open and closed incidents, completed
  runs with full transcripts, episodes, strategies with anti-patterns, approvals,
  and an audit history.
- **FR-016** The data MUST be coherent — a run must reference resources that
  exist, an episode must reference the run that produced it, a topology must
  connect resources that are related.
- **FR-017** Every demonstration record MUST be labelled as such, in the data and
  in the console.
- **FR-018** Demo mode MUST make no external call. Every provider response MUST
  come from a fixture, enforced by a transport that fails on a real request.
- **FR-019** Demo mode MUST be removable in one action, leaving nothing behind.
- **FR-020** Demo mode MUST refuse to enable on a deployment that already holds
  non-demonstration data, unless explicitly forced.
- **FR-021** Demo mode MUST be able to run a scripted investigation that streams
  as a real one does, so the live transcript can be seen without a model.

**Diagnostics**

- **FR-022** Every bring-up failure MUST produce a message stating what failed,
  why, and what to do, and the same message MUST be reachable afterwards from the
  console and the CLI.
- **FR-023** A support bundle MUST be producible in one command, containing
  versions, configuration with secrets removed, recent logs, self-check results
  and schema state.

### Non-functional

- **NFR-001** Bring-up to a signed-in console MUST complete within a declared
  budget on a modest machine.
- **NFR-002** Demo mode MUST populate within a declared budget.
- **NFR-003** The self-check MUST complete within a declared budget and MUST not
  hang on an unreachable dependency.
- **NFR-004** Nothing in this feature may weaken an authentication, authorisation
  or credential-handling property. The bootstrap path is a normal credential
  issuance with a short life, not an exception to the identity system.

## Success criteria

- **SC-001** An end-to-end test brings up a clean deployment, takes the printed
  credential, signs in, and reaches an authenticated page.
- **SC-002** The bootstrap credential expires after establishing a durable one,
  asserted.
- **SC-003** The bootstrap credential appears in no log, audit export or error
  message, asserted by a sweep.
- **SC-004** Bring-up run twice changes nothing.
- **SC-005** Every self-check finding names a problem and an action, asserted
  over every finding the check can produce.
- **SC-006** Model verification fails on an endpoint that answers but cannot tool
  call, with a message naming the actual limitation.
- **SC-007** Demo mode populates a coherent graph — every reference resolves,
  asserted.
- **SC-008** Demo mode makes no external call, enforced by a transport that fails
  the test on any real request.
- **SC-009** Demo removal leaves nothing, asserted by a full-table sweep.
- **SC-010** Bring-up, demo population and self-check each meet their budget.

## Out of scope

- The deployment topology itself, which feature 030 owns.
- The homelab-sized profile — feature 048.
- Synthetic scenarios used for evaluation — feature 049.

# ADR 0011 — Attribution lives in README and NOTICE only

- **Status:** Accepted
- **Date:** 2026-08-04
- **Deciders:** Project owner
- **Constitution impact:** Amends Article XIII (1.0.0 → 2.0.0)

## Context

Article XIII originally required three things at once: attribution in `NOTICE`, a
provenance header on every file containing reused code, and a per-module map
recording what was adopted, adapted, rewritten, or rejected. Feature 001
implemented all three, including a checker that cross-referenced headers against
the map and reported missing and orphaned entries separately.

Two problems surfaced once it was running.

**The obligation was over-served.** Apache 2.0 requires attribution. One
complete, maintained statement discharges that. What the repository had instead
was the same fact restated in a header on every configuration file, in a
conventions document, in a map, in the checker's own docstrings, and in its test
fixtures — each copy free to drift out of date, and none of them the one a reader
would look at first.

**A committed check depended on an uncommitted file.** The map lived in `docs/`,
which is planning material. The architecture-coverage test had the same shape and
the same flaw: it read a document outside the committed tree and `skip`ped when it
was absent. On a clean checkout it did not fail — it silently did not run, which
is the worst of the three possible outcomes.

## Decision

**Attribution is complete in `README.md` and `NOTICE`, and appears nowhere else
in the repository.**

Removed: per-file provenance headers, the header format convention, the
provenance map as an enforced artefact, and the `check-provenance` gate.

Added, as Article XIII clause 4: a committed file must not depend on an
uncommitted one. Where a committed artefact needs a rule that is written down in
planning material, the rule is restated in a committed file, and that copy
becomes the source of truth.

## Rationale

**One statement is more accurate than many.** A single attribution section gets
read, reviewed, and corrected. A hundred headers get copy-pasted, and the first
one to go stale is never noticed.

**The detail belongs where the decision is made, not in the shipped tree.** What
each prior system contributed is a design question, and design questions are
answered in ADRs and planning notes. A reader of the source wants to know what
the code does.

**Clause 4 closes a real hole, not a theoretical one.** Repointing the tier table
into the committed `AGENTS.md` turned a test that skipped on a clean checkout
into one that runs. The rule generalises: an enforcement mechanism that can be
disabled by a file's absence is not an enforcement mechanism.

## Consequences

**Positive**

- Attribution has one home, so it can be kept correct
- Every reference in a committed file resolves inside the repository
- `make verify` loses a check and keeps its meaning; the gate got shorter, not weaker
- The tier table now ships with the code that has to obey it

**Negative**

- No mechanical link from a reused module back to where it came from. Locating a
  fix in prior art becomes a manual search rather than a lookup.
- Nothing enforces that the attribution stays complete as more code is reused;
  that is now a review responsibility.

**Mitigations**

- The detailed record of what each prior system contributed is kept in the
  project's local planning material, outside the committed tree
- Reuse of a substantial module is called out in the commit that introduces it,
  where a reviewer will see it

## Alternatives considered

| Option | Why not |
|---|---|
| Keep headers, commit the map | Ships the planning material the repository deliberately excludes, and leaves the same fact in a hundred places |
| Keep headers, drop the map and the check | Unverified headers are worse than none: they carry the authority of a checked artefact with none of the checking |
| Drop `NOTICE` too | `NOTICE` is the standard Apache 2.0 attribution artefact and costs nothing to keep correct |

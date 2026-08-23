# ADR 0017 — The repository carries everything but a credential

- **Status:** Accepted
- **Date:** 2026-08-23
- **Constitution impact:** the article on attribution and repository contents —
  the clause forbidding a committed file from depending on an uncommitted one
  is replaced by a single rule about what may be committed
- **Supersedes:** the file-exclusion half of
  [0011](0011-attribution-in-readme-only.md); its attribution rule stands
  unchanged

## Context

The repository used to keep several classes of file out of version control on
purpose: the specifications and control files of every wave of work, the
scaffolding and the constitution that govern how that work is checked, the
module-level record of what came from where, and the working guidance an agent
reads before it starts.

The reasoning was that these describe how work is sequenced rather than what the
system is, and that a contributor cloning the repository needs the second and
not the first. A rule followed from it: a committed file must not depend on an
uncommitted one, because a link or a test pointing at an absent document
resolves to nothing in a fresh clone.

That reasoning held, and it cost more than it returned.

**The record of what was built lived outside the record of the build.** A
control file states what a feature's code actually proves, measured against the
code rather than against intent. It is the most useful artefact a wave produces
and the one nobody could read from the repository. Reviewing why something was
built the way it was meant asking whoever still had the directory on their
machine.

**Work performed in an isolated worktree could not write it down.** An excluded
directory does not exist inside a worktree. An agent working there cannot tick a
task, cannot write a control file, and — the failure that made this concrete —
does so silently, because writing to a path that is not there is not an error.
Three separate runs delivered their control file as a message instead, and one
of those messages was lost.

**The rule against depending on an uncommitted file made the writing worse.** It
forbade citing a requirement by its identifier, so a test comment said what a
task number was rather than what the test proved — and then the number itself
had to be scrubbed, twice, after review caught it in a committed file. The
prohibition existed to prevent a dangling pointer, and its practical effect was
prose that pointed at nothing at all.

## Decision

**Everything is committed except a credential.**

A password, a token, a private key, or a connection string carrying a secret is
never committed, never pasted into a commit message, an issue or a summary. A
live secret is read from the process that holds it, each time it is needed,
because a credential rotates and a copied one becomes a lie shaped like
documentation.

Machine state is excluded as housekeeping rather than as governance: caches,
installed dependencies, build output, agent worktrees and session state are
noise. They carry no decision and no evidence, and nothing is lost by their
absence.

Everything else ships: specifications, plans, task lists, control files,
confrontation reports, the constitution, decision records, provenance, and the
working guidance.

Two consequences follow directly. A committed file may link to a specification
and a test may read one, because both are present in the clone. And citing a
document is allowed without becoming obligatory — a file that answers "why" with
a pointer where it could answer with the substance is worse for the next reader,
and that obligation does not move.

## Alternatives considered

**Keep the exclusions and formalise the hand-off.** Have each isolated run
return its control file as text for an orchestrator to transcribe. This is what
was already happening, and it is where the loss came from: a report that does
not arrive takes the record with it, and a transcription is a copy that drifts
from the thing it copied.

**Commit only the control files.** Keeps the record and leaves the plans out.
But a control file is only legible against the tasks it reports on, so this
ships an answer without the question.

**Publish the material somewhere else.** A wiki or an artefact store keeps the
record without touching the repository. It also puts the record on a different
clock from the code it describes, and the two drift the moment one is updated
without the other. What makes a control file trustworthy is that it sits beside
the code it measured, at the same revision.

## Consequences

The repository grows by the accumulated planning material of every wave,
including screenshot evidence. That is a real cost in size and a real gain in
legibility, and it was accepted deliberately.

Guidance and checking documents that were previously local become reviewable —
which means they can also be wrong in public, and a stale one is now visible to
everyone rather than to one machine.

The scrubbing rule that removed requirement identifiers from committed source no
longer has a reason to exist. Substance still beats a pointer, and that is a
matter of writing well rather than a rule about what a clone contains.

One thing does not change: attribution for the Apache-2.0 work this project
draws on lives in `README.md` and `NOTICE`, is complete there, and is not
repeated elsewhere.

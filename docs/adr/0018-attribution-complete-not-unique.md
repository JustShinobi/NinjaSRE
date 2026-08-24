# ADR 0018 — Attribution must be complete, not unique

- **Status:** Accepted
- **Date:** 2026-08-24
- **Constitution impact:** the article on attribution — the clause forbidding
  attribution from appearing anywhere but `README.md` and `NOTICE` is replaced
- **Supersedes:** the uniqueness half of
  [0011](0011-attribution-in-readme-only.md); its completeness rule stands

## Context

The licence this project inherits obliges attribution. One complete, maintained
statement of it discharges that obligation, and this repository put that
statement in `README.md` and `NOTICE`.

A second rule was then added on top: attribution must appear **nowhere else**.
No per-file provenance headers, no provenance map, no "derived from" comments,
no aside naming a prior project. The reasoning was tidiness — a hundred
scattered half-statements are worse to maintain than one complete one, and each
of them rots separately.

The rule did not stay in its lane. It made a document that describes, module by
module, where each piece came from into a document that could not be committed —
so the repository carried the code and not the account of where the code came
from. It made "the substance, not the source" a rule rather than a preference,
so a comment that would have helped a reader trace a design back to what
inspired it was written without the trace. And when the surrounding decision
opened the repository to everything but a credential, this rule was what still
kept a genuinely useful record out.

None of that is what the licence asks for. The licence asks that the attribution
be complete where it lives. It says nothing about it living in only one place.

## Decision

**Attribution must be complete in `README.md` and `NOTICE`. It is no longer
forbidden anywhere else.**

A provenance record, a "derived from" note, an aside naming a prior project — all
allowed, wherever they help a reader. The maintained, complete statement stays
where it is and stays complete; a second mention elsewhere is a convenience for
whoever is reading that file, not a competing claim.

What survives from the old rule is a preference rather than a prohibition:
stating the substance is still better writing than citing a source in its place.
A comment that says what a mechanism does teaches more than one that says where
it came from. Where both help, both belong.

## Alternatives considered

**Keep the prohibition and exempt the provenance record.** An exemption list is
a rule nobody can predict the next case for — and the next case was already
waiting, because integration guides now point at vendor documentation.

**Drop the completeness rule too.** The licence obliges attribution; dropping
completeness would trade a maintenance preference for a licence problem.

## Consequences

The provenance record ships with the repository. Two architecture sweeps that
check reference surfaces — one for a stale catalogue size, one for a vendor
outside the validated scope — now treat it as a historical record rather than a
reference surface, the same way they treat a wave's planning directory. A record
of what was true at a moment is not a claim about what ships today, and holding
it to that standard would either make it false or make it silent.

Scattered attribution can rot. It is now possible for a "derived from" note to
name something that has since been rewritten. That is the cost, it is accepted,
and the guard against it is the same as for any other comment: the reader who
finds it wrong fixes it.

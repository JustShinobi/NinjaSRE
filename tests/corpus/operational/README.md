# A documentation corpus shaped like a real one

What a cluster's operational documentation looks like after two years, reduced
to the shapes that matter and rewritten so that nothing in it is real.

The tree is the fixture the corpus source is proved against, and its shape is
the assertion:

| Path | What is here | What the source does with it |
|---|---|---|
| `docs/runbooks/` | Four procedures, one of them the double-check queries, one of them carrying credential material | Ingested as runbooks; the one with credentials is refused |
| `docs/postmortem/` | Ten failures, including one pair that is the same failure twice | Ingested as post-mortems, with their fields extracted |
| `docs/adr/` | Three decisions | Ingested as architecture notes |
| `docs/analysis/` | One project document | Ingested as reference |
| `policies/firewall/` | Two rule sets, plus a `README.md` | The YAML is ingested as policy; the Markdown is not |
| everything else | `.env.local`, tofu state, a lockfile, a shell script, a `.txt`, a `.bak` | Never opened |

**The decoys are the point.** A repository holds fifteen thousand files and the
corpus is two directories of it. Every file outside `docs/**.md` and
`policies/**.yaml` is here so that a test can say the source did not read it,
rather than the source merely happening not to.

**Nothing here is a real value.** The credential material in
`docs/runbooks/backup-restore.md` and in `.env.local` is invented, matches the
shipped guardrail patterns, and exists so that ingestion can be seen refusing
it. Addresses come from the ranges the standards reserve for documentation and
every name is under `.invalid`, which can never resolve.

**The post-mortem pair is the acceptance fixture.** `2026-07-17` records the
failure without finding its cause; `2026-07-20` records the same symptom three
days later, names the cause, and says which entry it is a recurrence of. A
search for the symptom has to return both and has to make the second one
distinguishable as the one that explains it.

# surfaces/repl/ — the interactive session

**Tier 1.** May import: everything below. Must never import: `gateway`.

The REPL is for the engineer who is already in a terminal during an incident,
and for anyone debugging the platform itself. It drives the same core the CLI,
the API, the console, and the chat surfaces drive, and an investigation started
here produces the same result and the same trace as one started anywhere else.

## The prohibition

**A line beginning with a literal `/` is a slash command. Everything else goes
to the agent.**

No regex matching. No keyword table. No "that looks like a status request"
shortcut. No deterministic fast path for inputs that resemble a known command.
`routing.route` is the entire decision, and it is deliberately dull.

This is not a style preference. An intent shortcut answers without the agent,
and three things follow:

- **The answer is not in the trace.** "A conclusion carries the observations
  that support it" stops covering the answers that took the shortcut, and
  nothing announces which those were.
- **The evaluation suite cannot score it.** A scored run is a run that happened;
  a shortcut means the run being scored is not the one the operator experienced.
- **Surfaces diverge.** The same words typed into the REPL, the console, and a
  chat thread start behaving differently, and the difference is invisible until
  somebody compares two transcripts during an incident review.

The literal prefix is safe precisely because it is not a guess. Nobody starts a
sentence with `/` by accident, and when they do the cost is one
unknown-command message rather than a silently different investigation.

If a phrasing is common enough that routing it feels tempting, the answer is a
slash command with a good name — not a matcher.

## Conventions

- **A slash command never calls a model.** It is handed a `CommandContext` with
  no runtime, no LLM client, and no capability registry in it. A contract test
  counts LLM calls across the whole catalogue and fails on one.
- **A command sets a field; the loop acts on it.** `should_exit`,
  `cancel_requested`, `switch_to`. A command that called `sys.exit` would take
  the unsaved transcript with it, and one that swapped the session itself would
  leave the loop holding the old object.
- **Ctrl+C cancels the run, not the session.** Cancellation goes through the
  runtime's safe-point mechanism. A signal kill leaves evidence half-written and
  a run record that says "running" forever.
- **Ctrl+D is not Ctrl+C.** "I am finished" and "stop what you are doing" are
  different instructions, and conflating them loses a session to muscle memory.
- **Rendering derives from the event stream.** `streaming` renders pipeline
  events, not a second narration built alongside them, so anything on screen is
  something `runs replay` can reproduce.
- **The terminal is not an external surface.** Full error detail may be shown
  here — the person reading it is authenticated on the host and can read the
  logs anyway. Anything persisted or transmitted is still guardrail-filtered.
- **Questions and approvals are answered here.** An approval prompt appears at
  the surface the human is already using and never sends them elsewhere to say
  yes. Resolution goes through the interaction registry, which is where
  first-writer-wins lives.

## Where things go

- What a typed line is → `routing.py`. One decision, one place.
- The session loop, TTY detection, cancellation → `loop.py`.
- Reading a line, history, completion → `input.py`.
- The slash catalogue → `commands/`.
- Live rendering of an investigation → `streaming.py`.
- Inline questions and approvals → `interaction.py`.
- What survives leaving → `session.py`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../../AGENTS.md). Surface-wide rules
are in [`surfaces/AGENTS.md`](../AGENTS.md). This file records only what is
specific to the REPL.

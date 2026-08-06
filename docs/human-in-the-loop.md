# Human in the loop

The interaction layer between an investigating agent and the people around it:
the agent asking a question, somebody adding context mid-run, somebody taking
over, and every question or approval reaching the person at the surface they are
already using — and closing everywhere at once when it is answered.

This is the operator's guide, and the contract a surface implements.

## One abstraction, two things that look different

A question the agent raised and a change somebody has to approve are the same
situation seen twice: a run is suspended, N surfaces are showing something with
a button on it, a clock is running, and the first answer wins.

They are therefore one type — an **interaction** — and four properties are
implemented against it once rather than against each of them separately:

| Property | What it means |
|---|---|
| cross-surface closure | answering anywhere closes it everywhere, inside a stated budget |
| persistence | a pending interaction survives a restart, answerable or clearly expired |
| concurrency resolution | two people answering at once resolve to one; the second is told who won |
| attention state | a run waiting on somebody is distinguishable in a listing |

Implementing them twice is not hypothetically worse. It fails in a predictable
way: one of the two gets persistence and the other does not, one closes
cross-surface and the other leaves a live button in a chat thread for a week —
and it is never the same one, so people learn that "answered elsewhere" behaves
differently depending on what they were answering.

### The four states

| State | Meaning | What a surface does |
|---|---|---|
| `pending` | somebody is still being waited on | show it, with a way to answer |
| `answered` | a person decided | stop offering to answer; show what was decided |
| `expired` | the window closed with no answer | stop offering; say it timed out |
| `superseded` | it stopped applying — the run concluded, was cancelled, or a person took over | stop offering; say it no longer applies |

`expired` and `superseded` are deliberately different. "This timed out" invites
somebody to raise it again; "this no longer applies" does not.

Whether an approval was *granted* is not a state. A rejected approval and a
question answered "no" are both `answered`, because the surface's obligation —
stop showing a button — is identical.

## Questions the agent asks

The agent reaches a point where an inference would be a guess, and asks. The
question appears at the surface the investigation came from, plus whichever
surfaces the team configured for escalation. The loop suspends. The first answer
from anywhere resumes it.

### The agent may not ask for a credential

A question that asks somebody to disclose a password, key, token, or any other
credential is **refused at the capability boundary**, before it is shown to
anybody.

This is not belt-and-braces. Credentials are held by the credential proxy and
injected at the network edge precisely so that nothing above that layer ever
sees one; the cheapest way around that is not an exploit, it is to ask a person
to paste one into a chat thread — where it would then live in the transcript,
the run trace, the episode written from the trace, and the channel's retention.

The refusal is narrow on purpose. A question that *mentions* a credential is
fine — "was the API key rotated at 11:58?" is a legitimate question about the
world. What is refused is asking for the value. Refusing the whole subject would
teach the agent that credentials are undiscussable rather than undisclosable.

Answers are screened by the guardrail engine on the way in, which is the second
line: somebody who volunteers a secret in reply to an innocent question has it
redacted before the agent, the transcript, or the store sees it.

### Timeouts

A question has a window. When it closes, the agent is told the answer is
**unavailable** — never given a default, never given a guess.

An agent that learns it gets a plausible answer when nobody replies has learned
that asking is optional, and it will stop asking exactly when the question
mattered. An investigation that concludes with a stated uncertainty is worth
more than one blocked indefinitely on a question nobody saw.

| Setting | Constant | Default | What it decides |
|---|---|---|---|
| Question window | `HANDOFF_TIMEOUT_SECONDS` | 15 min | how long the loop waits for an answer |
| Interaction expiry | `INTERACTION_EXPIRY_SECONDS` | 15 min | how long an interaction stays answerable |
| Closure budget | `INTERACTION_CLOSURE_BUDGET_SECONDS` | 5 s | how long closure may take to reach every surface |

Shorten the window for a deployment whose incidents are answered in minutes.
Lengthen it and you are choosing to have runs sit suspended; the run still
concludes either way, so the trade is between a longer wait and a weaker answer.

### Escalation surfaces

Routing is origin-first, then escalation, deduplicated. The person who started
the investigation is most likely to know, and a routing order that put them
third is a question they see after somebody else has already been paged.

A question raised in a channel the requester has left still reaches the
escalation surfaces, and the fact that the origin could not be reached is
recorded rather than swallowed.

## Adding context to a running investigation

Anyone, from any surface, can add context to a run that is already going.
Messages are **debounced and merged** into one numbered guidance block at the
next turn boundary.

```
Turn N executing
  ├─ "check the deploy at 14:32"
  ├─ "also the cache cluster"        } within the debounce window
  └─ "ignore the DB, we ruled it out"
Turn N ends → drain and merge:

  Additional guidance from the operator:
  1. check the deploy at 14:32
  2. also the cache cluster
  3. ignore the DB, we ruled it out

Turn N+1 begins with the block in context.
```

Numbering preserves ordering, which matters because later messages usually
correct earlier ones. Delivering the three separately would make the model read
the last as a correction of the first two.

Three things to know as an operator:

- **You get a receipt.** When the run reads your guidance, the surface you typed
  into says so. Somebody who types and sees nothing types it again.
- **Guidance carries no authority.** It is direction for the investigation, not
  a way to change what the agent is allowed to do. Context added after the final
  tool-stripped turn does not give tool access back.
- **It is screened.** Queued text goes through the same guardrail ruleset as
  everything else, on the way in rather than at the merge.

`MESSAGE_QUEUE_DEBOUNCE_MS` (default 1.5 s) is the window. Raise it for a team
that types in long bursts; lower it if guidance is arriving noticeably late.

## Taking over

Takeover is **not** cancellation, and the difference is the whole point.

Cancelling and then fixing the problem by hand produces two records of one
incident: a run that stopped saying nothing useful, and a set of actions in
somebody's shell history. Nothing connects them, so the trace cannot be
reviewed and the episode written from it is wrong.

Taking over instead:

1. the run **pauses at a safe point** — between iterations, never mid-call;
2. in-flight sub-agents are **reaped**, so nothing else is changing the system
   while you are;
3. everything the run was waiting on is **closed**, so no stale button is left
   on a surface for a run you are now driving;
4. your actions are **recorded under your own principal, in the same trace**;
5. you either **resume** — the agent continues with your actions in its context
   — or **conclude** the investigation yourself.

### The procedure

- **Take over** naming yourself and, ideally, why. A run already under takeover
  refuses a second one: two people driving is how two conflicting changes get
  made.
- **Record what you do** as you do it, with the outcome. An action recorded
  against a run nobody took over is refused, because an action in a trace with
  no interval around it reads to a reviewer as one nobody authorised.
- **Resume or conclude.** Resuming puts your actions into the agent's context
  framed as changes that have already happened — not as evidence it gathered,
  and not as instructions. Concluding marks the run *completed*, because
  somebody handled the incident and that is a conclusion.

A resumed agent is told to re-check anything it measured before your changes.

## Progress and attention

Two mechanisms, for two different questions.

**Attention** answers "which of these runs needs me". A run waiting on a
question, an approval, or both is distinguishable in a listing, with how long it
has been waiting and what for. The listing is ordered longest-ignored first,
which is what stops the question nobody noticed from staying unanswered. A
finished run needs nobody, whatever it last recorded.

**Progress** answers "is it still working, or is it wedged". A run past the
configured interval reports that it is still going — elapsed time, steps,
evidence gathered. Deliberately not what it currently believes: a half-finished
hypothesis put in an incident channel is what everybody starts working from.

| Setting | Constant | Default |
|---|---|---|
| Progress interval | `PROGRESS_NOTIFICATION_INTERVAL_SECONDS` | 5 min |
| Progress cooldown | `PROGRESS_NOTIFICATION_COOLDOWN_SECONDS` | 10 min |

The cooldown is the half that matters. A run long enough to need progress
reporting is long enough to produce a notification every turn, and a channel
that gets one of those is muted before the notification that mattered. Raise the
cooldown before you raise the interval.

A run already waiting on a human is **exempt** from progress notifications:
somebody has been asked, on a surface that is already showing it, and telling
them the run is still going repeats what their own unanswered question says.

## What a surface has to implement

Two obligations, and the second is the one that is easy to skip.

```
name              what this surface is called
present(...)      show an interaction to this surface's audience
closed(event)     stop offering to answer the interaction this event closes
```

Rules a surface must honour:

- **Close on every kind of closure**, not only on an answer. A question that
  expired or was superseded is one you have to stop showing a button for exactly
  as much as one that was answered — and those are the stalest ones.
- **Do not carry the authority.** A surface reports who answered; it does not
  decide whether they may. The decision goes back through the core, which
  re-checks. A design where forwarding a message forwards the ability to approve
  is not one.
- **Fail alone.** Your failure to close is logged and reported; it does not stop
  the other surfaces closing. Expect to be told about it rather than to take
  everything else down with you.
- **Expect to lose.** Two people answering at once resolve to one. The losing
  surface is handed who won and what they said, and should show that rather than
  only "too late".
- **Answer with a principal.** An answer with nobody's name on it is not
  attributable, and a conclusion resting on it cannot be followed up.

A surface not named on an interaction is not told about it. Interactions travel
only to the surfaces a team routed them to.

## Failure modes worth knowing

| What happens | What the system does |
|---|---|
| A surface is down when a closure goes out | the others still close; the failure is reported, not swallowed |
| The same closure is published twice | the second is dropped — one announcement per interaction |
| A question is raised with no surface attached | it is asked, gets nothing, and the run records the gap |
| The channel a question came from was archived | escalation surfaces still receive it |
| An answer arrives after the run concluded | the interaction was superseded; the answerer is told it no longer applies |
| A sub-agent will not stop during a takeover | the pause proceeds and you are told a specialist may still be running |
| A session record holds an unreadable interaction | it is dropped with a log line rather than failing the whole resumption |

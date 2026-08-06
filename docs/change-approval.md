# Change approval and security policies

One review queue for every change worth reviewing, and the organisation-level
policy that decides what goes into it. This is the operator's guide: designing a
policy, setting reviewers up, resolving conflicts, and tuning expiry.

## The shape of it

Five kinds of change go through one mechanism.

| Change type | What it changes | Who usually proposes it |
|---|---|---|
| `configuration` | a node's own settings | an engineer editing their team's configuration |
| `prompt` | what an agent is told to do | a platform engineer, an SRE lead |
| `capability` | which tools an agent may call | a platform engineer |
| `knowledge` | a document entering the corpus | an agent, after an investigation |
| `remediation` | an action against production | an agent, or a responder |

They are one mechanism rather than five because they are the same problem: a
proposal, a reviewer, a decision, and a record that outlives both people. Five
mechanisms would have drifted, and the one nobody looked at twice would have
ended up the weakest.

A change that is gated does not take effect when it is written. The current
value stays in force, the proposal enters the queue, and it applies only when
somebody with standing decides it.

## Designing a policy

Nothing is gated until you say so. A fresh deployment gates nothing, because a
first configuration change sitting in a queue with no reviewer is a worse
starting state than an ungated one.

| Setting | What it does |
|---|---|
| `require_approval_for` | which change types are queued rather than applied |
| `require_approval_for_side_effect_levels` | which classes of production action need a human, by name |
| `allow_self_approval` | whether the requester may also be the approver — **defaults to forbidden** |
| `locked_settings` | paths no node may override, however senior the person editing |
| `max_values` | numeric ceilings |
| `required_settings` | paths that must hold a value and cannot be cleared |
| `allowed_values` | closed sets of permitted values per path |
| `token_expiry_days`, `token_warn_before_days`, `token_revoke_inactive_days` | the token lifecycle the identity layer applies |
| `change_expiry_hours` | how long a queued change stays answerable |
| `log_all_changes` | the audit verbosity floor |

### Gate what matters, not everything

Approval fatigue is how this control fails in practice. A reviewer who is asked
to approve forty changes a week approves the forty-first without reading it, and
that is the one that mattered. Gate the change types whose blast radius is wide
— prompts and capability enablement usually are — and leave a team's own
budgets and thresholds ungated.

### Ceilings bind everybody, including you

A maximum, a lock, a required setting, and an allowed-value set are refusals,
not gates. They apply to every role, the owner included. There is no path that
consults who is asking, because a ceiling with an exemption is a ceiling for the
people it was not written for.

To raise a limit, change the policy. That is itself audited, and it can itself
be approval-gated.

### Changing a policy never rewrites the past

- Changes **already approved** keep their effect. Nothing is retroactively
  undone.
- Changes **already queued** stay queued. They are neither auto-applied nor
  auto-discarded.
- Each queued change is **re-checked against the policy in force when somebody
  decides it**. A change that was legal when it was written and is not legal now
  is refused at the decision, with the violation named.

Before you save a policy change, the console shows you which change types start
and stop being gated and which limits tightened or relaxed. Read that sentence:
it is computed from the change you are about to make, not from this document.

## Setting reviewers up

There is no reviewer list to maintain. A reviewer is whoever holds
`approval.review` at the node the change takes effect at — the `responder` role
and above — resolved through the same configuration hierarchy everything else
resolves through.

That means:

- a grant at `payments` covers changes at `payments` and everything beneath it;
- a grant at `platform` does **not** cover changes at `payments`;
- somebody offboarded stops being a reviewer the moment their grant goes, with
  no list to prune.

**Permission is re-checked when the decision is made**, not only when the change
was queued. A reviewer who lost the permission in between cannot approve, and a
change queued last week cannot be approved by somebody who left on Monday.

### Self-approval

Forbidden by default, and the refusal reads both principals: acting *as* the
requester through impersonation is refused, and so is the requester hiding
behind somebody else's identity.

For a single-operator deployment, set `allow_self_approval` to true
deliberately. The default is strict because the multi-person case is the one
where the control does anything.

### When nobody can review

If the only person eligible is the person who asked, the change reports that
rather than reporting an empty reviewer list. "Only the requester is eligible"
is something you can act on; "nobody is eligible" is not.

## What a reviewer sees

Three things, in this order.

**The blast radius**, first and above the diff. How many nodes and teams the
change would reach through inheritance, and how many already set their own value
and are therefore unaffected. The scope decides how carefully somebody reads,
and a reviewer who learns it afterwards has already decided how much attention
to spend. If the hierarchy could not be read, this says the scope is *unknown* —
which is not the same as saying it is small.

**The diff**, rendered for the kind of change it is. Configuration is diffed by
path; a prompt is diffed by line; a capability change is a set difference; a
knowledge proposal is the document laid out to be read; a remediation is its
steps beside its rollback plan.

**The requester and their rationale.**

### Large diffs

Above two hundred lines, the diff is summarised — never truncated silently. The
summary says that it is a summary, how many changes it is showing out of how
many, and how many lines each section left out. Any section can be expanded
whole. A ten-thousand-line change stays reviewable, and a reviewer is never
shown something that looks complete and is not.

Every value in a diff passes the secret scanner before it is displayed *and*
before it is recorded. A credential pasted into a configuration field by mistake
does not survive into the audit trail.

## Resolving conflicts

A change carries a fingerprint of what its target looked like when it was
queued. At the decision, that is compared against what the target looks like
now. This is the control that stops a reviewer approving a description of a
world that no longer exists.

| What happened | What you see | What to do |
|---|---|---|
| Somebody edited the target in between | the change is marked **conflicted**, naming the divergence | re-review it, then decide |
| Another change to the same target was approved first | the remaining ones are marked **conflicted**, naming the change that won | re-review or reject |
| The target was deleted | **conflicted**, and unrecoverable | reject it; there is nothing left to apply it to |
| Two reviewers decided at once | the first decision stands; the second is told what was decided | reload the queue |

**Conflicted is not rejected.** The change is still open and still needs an
answer — it just has to be answered against what the target says now. Re-review
re-fingerprints it and replaces the "current" side of the diff, so the next
reviewer is looking at a real comparison rather than at history.

A deleted target is the exception: re-review is refused, because approving it
would produce an authorisation that could never be honoured.

## Tuning expiry

A queued change expires after `change_expiry_hours` — three days by default,
thirty days at most. When it expires it is **closed, never applied**, and the
requester is told.

The default is long because a prompt change is not something anybody should be
asked to approve during an incident. Remediation approvals are the opposite case
and carry their own, much shorter window.

Set it shorter if your queue is small and you want stale proposals to clear
themselves; set it longer if reviews genuinely take a week. A change nobody
answered in a month is one whose reviewer has forgotten what the system looked
like when it was proposed, which is why there is a ceiling.

## Where a decision shows up

A decision made anywhere closes the request everywhere. The console, Slack,
Discord, and Teams all subscribe to one decision event rather than each keeping
their own copy of the state, so a change approved in the console does not leave
a live button in a chat channel for the rest of the week.

A decision is published exactly once, so a retried approval does not produce a
second announcement.

## The record

Every stage is audited: queued, decided, expired, and conflicted.

The decision record retains **the diff that was decided about**, not a pointer
to the target. Months later, the question somebody asks is "what did the person
who approved this actually see", and a record that pointed at current state
would answer a different question every time it was asked.

The record names the requester and the approver, both, and carries the rejection
reason when there is one. Getting the audit trail out is covered in
[`identity-and-audit.md`](identity-and-audit.md).

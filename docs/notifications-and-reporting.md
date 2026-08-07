# Notifications and reporting

What an investigation produces, where it is delivered, and who gets woken up.

Two layers, kept separate because they answer different questions:

- **Reporting** (`platform/reporting/`) turns a concluded investigation into a
  document and delivers it to every destination the team configured.
- **Notifications** (`platform/notifications/`) decides whether a human should
  be interrupted, at what urgency, and through which route — and records every
  time it decided *not* to.

The report is the thing somebody reads. The notification is what gets them to
it. A deployment can have either without the other.

---

## Setting up a destination

A destination is where a finished report is delivered. Thirteen are supported,
grouped into five rendering classes:

| Class | Destinations | Shape |
|---|---|---|
| chat | Slack, Microsoft Teams, Telegram, Discord | Conclusion first, working underneath |
| ticket | Jira, GitHub, GitLab, PagerDuty | Actions directly after the conclusion |
| document | Confluence, Notion, Google Docs | Postmortem headings, postmortem order |
| markdown | Local Markdown | `report.md` on disk — the canonical full version |
| email | Email | HTML with a plain-text alternative |

Destinations are configured per team through the configuration service, under
`surfaces.report_destinations`:

```yaml
surfaces:
  report_destinations:
    - kind: slack
      target: "#incidents"
      audience: private
      verified: true
    - kind: jira
      target: OPS
      audience: team
      verified: true
    - kind: local_markdown
      target: /var/lib/ninjasre/reports
      verified: true
```

`kind` may also be one of the generic values this section has always accepted
(`chat`, `webhook`, `email`, `pull_request_comment`, `knowledge_base`). A
generic kind needs the deployment to say which named destination it means; one
with no mapping is **skipped and logged**, never guessed.

### Verify before you depend on it

**`verified: false` destinations are refused.** That is deliberate: an
unverified destination fails at 03:00, which is the worst possible time to find
out an API token is wrong.

Verification runs a probe per destination kind and reports the vendor's own
reason for refusing — "the API token is not valid for this workspace" sends you
to the right settings page in a way "verification failed" does not. A
destination whose kind has *no* probe is reported as unverifiable rather than
assumed working.

### Audience

`audience` decides two separate things:

| Audience | Masked identifiers | Evidence bodies |
|---|---|---|
| `private` | restored to real names | shown |
| `team` | left as tokens | shown |
| `public` | left as tokens | omitted; only identifiers and sources |

A token left in place is meaningless without the run's mapping, which is exactly
what makes leaving it the right answer for a wide channel rather than a degraded
one. The default is `private`, and widening it is a deliberate edit.

### Size limits

Every destination declares the body size it accepts. A report over that limit is
**summarised with a link to the full version**, never cut. A truncated report
reads exactly like a short one, so a reader never learns that the section
answering their question was the part that did not fit.

The summary keeps the title, the conclusion, and the recommended actions, and
carries a sentence saying it is a summary and where the whole thing is. If even
that will not fit — a PagerDuty note, for instance — the delivery degrades to
the title and the link, and finally to the link alone.

### When a destination stops working

Three consecutive failures mark a destination **unhealthy**. Deliveries to it
are then skipped, with a recorded reason, for fifteen minutes; after that it is
tried again. The expiry is deliberate — a rotated token starts working on its
own, and a state only a human can reset is a state that stays set.

A single destination's failure never affects the others. Every delivery is
isolated, including from a transport that raises something nobody declared.

### Retries and duplicates

Transient failures retry with backoff, up to four attempts. Every attempt
carries the same **idempotency key** — the run and the destination — so a vendor
that took the first copy and failed to answer does not receive a second. A
permanent refusal (a deleted channel, an archived project, a deleted team) is
recorded once and not retried.

Every outcome is written to the run trace as a `report_delivered` event, one per
destination. "Did the Jira ticket get created" is the question people ask the
morning after, and a single run-level "reports delivered" cannot answer it.

---

## Designing a notification policy

### Sinks

| Sink | What it is for |
|---|---|
| **Pushover** | Direct phone push, independent of any chat platform |
| PagerDuty | Paging for critical outcomes |
| Chat | In-channel notification where the incident is already being discussed |
| Email | Non-urgent summaries; deliberately not a paging route |
| Webhook | The operator's own automation, given fields rather than prose |

Pushover is called out because of what it does *not* depend on. A team without
Slack has nowhere for a chat notification to go, and an escalation about an
incident *in* the chat platform must not travel through the chat platform.

```yaml
surfaces:
  notification_sinks:
    - kind: pushover
      target: "<user or group key name>"
      verified: true
      options:
        device: phone
        sound: persistent
    - kind: chat
      target: "#incidents"
      verified: true
```

No credential appears in configuration. The transport holds a tenant-scoped
handle and the credential proxy injects the secret at the network edge, which is
why a sink is safe to store in configuration and to print in a health report.

### Routing

Severity and outcome choose the sinks:

| Severity | Reaches |
|---|---|
| critical | PagerDuty, Pushover, chat, webhook |
| high | Pushover, chat, webhook |
| medium | chat, webhook |
| low | chat, email, webhook |
| noise | nobody — recorded as having reached nobody |

A **resolved** outcome never wakes anybody, whatever the incident's severity was
while it was open.

Pushover priority follows severity: critical is `emergency` (repeats until
acknowledged), high is `high`, medium is normal, low is quiet. Nothing below a
critical outcome may reach `emergency` — a platform that emergency-pages for a
medium finding trains its users to turn Pushover off, and then it is not there
on the night it is needed.

### Quiet hours

```yaml
surfaces:
  notification_policy:
    quiet_hours_enabled: true
    quiet_hours_start: 22
    quiet_hours_end: 7
    timezone: Europe/Lisbon
```

Inside the window, a non-critical notification comes **off** the paging sinks
and goes to the ones that do not wake anybody. It is still there in the morning.
A critical outcome ignores the window entirely — quiet hours are about sleep,
not about severity.

The timezone is the team's own. A window evaluated in UTC wakes a team in
Auckland at lunchtime and never wakes one in Los Angeles.

### Cooldown

The same team, subject, and severity stays quiet for fifteen minutes after a
notification about it (five for critical). Severity is part of the key on
purpose: an incident that was medium an hour ago and is critical now is not the
same notification, and suppressing the second because of the first is the exact
failure a cooldown is meant to prevent rather than cause.

```yaml
surfaces:
  notification_policy:
    cooldown_seconds: 1800
```

A team may **lengthen** its cooldown. It cannot shorten it below the platform
default — the ceiling is what stops one misconfigured team becoming the
deployment's paging load.

**Every suppression is recorded.** That is most of the point. A cooldown that
quietly drops notifications is indistinguishable, from the outside, from a
notification system that is broken, and the first time anybody looks is after an
incident nobody was told about. The record says what would have been said, when,
and until when the window runs.

### Rate limits

```yaml
surfaces:
  notification_policy:
    notifications_per_hour: 12
```

Bounded per team, across every sink — a human's attention is the scarce
resource, and it is not five times less scarce because five sinks are
configured. A team may narrow this; the schema refuses a value above the
platform ceiling.

Refusals are recorded and the teams that hit the limit are named. A team being
rate-limited is a team whose alerting produces more than a person can act on,
which is a tuning problem somebody should be told about.

### Tuning, in order

1. Start with everything at the defaults and watch the suppression record for a
   week.
2. If a team is being rate-limited, the alerting is too noisy — fix that before
   raising anything here.
3. If the same subject suppresses repeatedly, lengthen its cooldown rather than
   muting the sink.
4. Turn on quiet hours only once severity routing is right. Quiet hours divert
   *non-critical* notifications; if too much is being classified critical, quiet
   hours will not help.

---

## Escalation

An attention item nobody addressed escalates after ten minutes, to a configured
sink, at one severity higher than the notification that went unanswered.

**It is cancelled when the underlying item resolves.** An approval granted at
minute nine must not page somebody at minute ten: an escalation that fires after
resolution trains people to ignore escalations, and an escalation people ignore
is worth less than none, because it also costs the interruption.

Escalation is bounded — two rounds, then it stops. One that repeats for ever is
a notification the recipient filters, at which point the next one is filtered
too.

Nothing here owns a timer. The registry answers "what is due at this instant",
and whatever drives the deployment's clock asks it.

---

## What a report contains

| Section | Content |
|---|---|
| Summary | One paragraph an on-call engineer can act on |
| Root cause | The conclusion, with an explicit confidence band |
| Causal chain | The mechanism, step by step |
| What the evidence supports | Each claim with the evidence entry behind it |
| Not confirmed | Hypotheses the evidence did not confirm |
| Ruled out | What was considered and eliminated, and why |
| Recommended actions | Immediate, short-term, preventive |
| Run detail | Capabilities used, duration, cost, link to the run |

Three properties are enforced rather than encouraged:

- **A validated claim carries its evidence.** A claim citing an identifier the
  run does not hold is filed as *non-validated*: the model invented a reference,
  and shipping it with the word "validated" on it would be worse than dropping
  it.
- **Confidence is derived from the score, never asserted.** No formatter can
  promote a hedge into a finding by choosing a friendlier word.
- **"No conclusion" is stated plainly.** A report that hedges its way to a
  plausible-sounding cause is worse than one that says "I could not determine
  this, here is what I ruled out" — the second saves the next engineer the work
  of re-ruling-out.

Reports pass the guardrail engine **before** any formatting, so one screened
value feeds all thirteen formatters and a destination cannot be the one that
skipped it. Redaction for a particular readership happens separately, at the
sink.

---

## Troubleshooting

**"The report did not arrive anywhere."** Check `verified` on the destination
first — an unverified destination is skipped by design, and the reason says so.
Then check destination health: three consecutive failures mark it unhealthy for
fifteen minutes.

**"The report arrived truncated."** It did not; it arrived summarised, and the
body says so and carries a link. If the link is wrong, the run link on the
report's metadata is what a summary points at.

**"Why wasn't I told?"** The suppression record and the rate-limit report answer
exactly this. Every decision that sent nothing is a `notification_decided` event
on the run, with a reason.

**"We are being paged for things that do not matter."** Severity routing first,
cooldown second, quiet hours third. Raising the cooldown to hide a severity
problem hides the next real page too.

**"An escalation fired after we had already fixed it."** The item was never
resolved in the registry. Whatever closes the underlying approval or question
has to call `resolve` — cancellation is a write, not an inference.

# Guardrails and masking

Two controls sit at the boundary between NinjaSRE and everything outside it, and
they solve different halves of the same problem.

**Masking** replaces your infrastructure identifiers — pod names, cluster names,
account IDs — with stable tokens before a prompt reaches a model you do not
host, and puts them back when a human who is entitled to see them reads the
report. It is reversible.

**Guardrails** scan every string the platform is about to store or transmit and
redact, refuse, or record it by rule. They are not reversible, because the
things they catch are secrets that should not have been there.

The credential proxy already keeps the credentials NinjaSRE *manages* away from
the agent. These two are for everything else: the identifiers that are
legitimately in the agent's reach, and the secrets that turn up in *data* — a
connection string in a log line, a token in an error message.

---

## Masking

### Choosing a level

| Level | What it replaces | When it is right |
|---|---|---|
| `off` | Nothing | The provider is already trusted with your infrastructure names — a self-hosted endpoint, or a data processing agreement that covers this. |
| `standard` | Pods, clusters, namespaces, hostnames, IP addresses, cloud account IDs, ARNs | **The default.** Everything structurally identifying, nothing that carries meaning the model reasons with. |
| `strict` | Everything in `standard`, plus service and deployment names and your own patterns | A regulated environment where a service name is itself sensitive. Costs investigation quality — see below. |
| `local_models_exempt` | `standard` against a hosted provider, `off` against one running on your own machines | A deployment that routes some turns to a local model and some to a cloud one. Resolved per call, from the provider the call is actually going to. |

```bash
export NINJASRE_MASKING_POLICY=standard
```

### What the level costs you

Masking is not free, and the cost is not evenly distributed across the levels.

A token is a fact the model reasons about at one remove. At `standard` that
barely matters: `NSRE_MASK_POD_1` is as good a handle as
`checkout-7d9f8b6c5d-x2n4p` for every question an investigation asks about a pod,
because the pod's *name* was never the evidence.

At `strict` it starts to matter, because service names carry meaning. A model
told that `checkout` is failing has a different prior than one told that
`batch-reconciler` is failing — one is user-facing and one is not, and the
model knows that without being told. Replace both with `NSRE_MASK_SERVICE_1` and
`NSRE_MASK_SERVICE_2` and that prior is gone.

This is why `standard` is the default and `strict` is not, and why the
evaluation suite runs both. Set `strict` because your environment requires it,
not because more masking sounds safer.

### Tokens are stable within a run

The same identifier gets the same token everywhere it appears — in a metrics
result, in a log line, in the alert that started the run. That stability is what
makes a masked investigation possible at all: correlating one pod across two
evidence sources *is* the investigation, and a model that cannot tell two tokens
are the same pod cannot do it.

Tokens are `NSRE_MASK_<KIND>_<n>`. The kind is in there deliberately — a model
reasons better about `NSRE_MASK_POD_3` than about `NSRE_MASK_3`.

### The mapping is a secret

The token-to-identifier table is the key to everything the tokens hide. It is
stored with the run, never transmitted, never rendered into a report, and its
`repr` deliberately names nothing so it cannot leak through a traceback. What
gets recorded in the run trace is a count per kind, which says masking worked
without saying what it hid.

### Restoration

Reports are restored before a human who is entitled to the identifiers reads
them, so what lands in your incident channel names the real pod. A destination
whose readers are *not* entitled — a channel with mixed membership — keeps the
tokens, which are meaningless without the mapping.

A token the model invented rather than one NinjaSRE issued is left exactly as it
is. Resolving it would put a real pod name into a sentence that was never about
that pod, and nobody reading the report could tell.

### Adding your own patterns

Custom patterns apply at `strict`. Each one needs a name, because that is what a
rejection will quote back at you, and a `value` group, because that is the part
that gets replaced:

```python
CustomPattern(name="ticket", pattern=r"(?P<value>\bINC-[0-9]{4,8}\b)")
```

Patterns are validated when they load, not when they run — see
[Writing patterns that will be accepted](#writing-patterns-that-will-be-accepted).

---

## Guardrails

### Where they apply

Three points, because they are three different threat surfaces:

| Point | What it protects against |
|---|---|
| `pre_tool_use` | **Exfiltration.** A secret the model read in one tool's output being put into another tool's arguments. This is the only point that can refuse a call. |
| `post_tool_use` | **Poisoning and persistence.** A tool result becomes evidence, and evidence is stored, summarised, and eventually published. |
| The sink boundary | **Publication.** Anything transmitted, rendered, or written to the database. |

### The three actions

- **`redact`** replaces the match with the rule's `replacement` (`[REDACTED]` by
  default) and lets the operation proceed.
- **`block`** refuses the operation. At `pre_tool_use` the model receives a
  structured refusal naming the rule — never quoting what it matched — so it can
  route around the refusal rather than repeat it.
- **`audit`** records the match and changes nothing. This is how you watch a new
  rule before you enforce it.

### Writing rules

Point `NINJASRE_GUARDRAIL_RULES_PATH` at a YAML file:

```bash
export NINJASRE_GUARDRAIL_RULES_PATH=/etc/ninjasre/guardrails.yml
```

```yaml
rules:
  - name: internal-ticket-id
    description: Our ticket identifiers are not for a third party.
    action: redact
    replacement: "[TICKET]"
    keywords: ["inc-"]
    patterns:
      - '\bINC-[0-9]{4,8}\b'
```

| Field | Meaning |
|---|---|
| `name` | Required and unique. What the audit trail reports and what you disable a rule by. |
| `description` | For whoever reads the file next. |
| `action` | `redact`, `block`, or `audit`. Defaults to `redact`. |
| `replacement` | What a redaction leaves behind. Defaults to `[REDACTED]`. |
| `keywords` | Lowercase substrings. If none appear in the text, the rule's patterns are not run at all — this is what keeps a large ruleset affordable on a large payload. Omit it and the patterns always run. |
| `patterns` | Required, non-empty, a list of regular expressions. |
| `enabled` | Defaults to true. |

An unknown field is an error rather than something quietly ignored, because a
misspelled `patern:` is a rule you believe is running and is not.

### Your rules are merged onto the shipped ones

NinjaSRE ships rules for common secret shapes — AWS keys, private keys,
connection strings, JWTs, GitHub and Slack tokens, and a labelled-secret
catch-all. Your file is merged onto them **by name**:

- A name that does not exist is **added**.
- A name that already exists **replaces** the shipped rule, keeping its position.

So a file that mentions only your rules does not remove the shipped ones — and
disabling a shipped rule is a matter of repeating its name:

```yaml
rules:
  - name: json-web-token
    description: We index JWT headers deliberately and need them intact.
    enabled: false
    patterns: ["never-matches"]
```

### Reloading

The file is re-read when it changes, within a second, with no restart. Rules get
tuned during incidents by whoever is on call, and a control that needs a
deployment to change is a control that gets bypassed instead of adjusted.

**A file that will not parse does not disarm the platform.** The last set that
loaded stays active, and the failure is logged and reported. NinjaSRE never runs
with no rules because somebody left a tab in a YAML file.

If a reload is being refused, the reason is in the `guardrails.ruleset_rejected`
log line, and it names the rule and the field.

### Overlapping matches

Two rules matching overlapping spans collapse into one. The merged span is
attributed to the **widest individual contributing match**, and its action is the
**most severe** among the contributors — so a narrow `block` cannot be switched
off by writing a wide `audit` over it. Both resolutions are deterministic, which
is what makes an audit trail reproducible.

### What gets audited

Rule name, action, location, match count, and whether the operation was refused.
**Never the matched text**, for any action — including `audit`. The audit table is
append-only and exempt from retention, which makes it the worst possible place
in the deployment for a secret to end up.

If you need to see what a rule actually matched, reproduce it locally: the CLI
is not treated as an external surface and keeps the whole line.

---

## Writing patterns that will be accepted

Both masking patterns and guardrail patterns run against text somebody outside
your organisation wrote — a log line, an error message, a tool result. A pattern
that backtracks is therefore a denial of service reachable by *writing a log
message*, with no authentication in front of it.

So patterns are validated when they load, and rejected with a reason:

- **No unbounded quantifier inside a repeated group.** `(a+)+` and `(\s*)*` are
  the shape that goes exponential. Bound the inner repetition — `{1,64}` rather
  than `+` — and it becomes linear.
- **Nothing that is measurably slow.** Every candidate is timed against short
  runs of its own alphabet at increasing lengths.

A rejection names the rule or pattern so you know which of the six you just
added is the problem.

---

## The local CLI is not an external surface

Redaction happens at the sink, not at the point a failure is constructed. That
placement is deliberate:

| Destination | Guardrails | Exception detail | Identifiers |
|---|---|---|---|
| CLI, REPL | Recorded, not applied | Full | Restored |
| REST API, chat, web console, reports, the database | Applied | Type name only | Restored only for an authorised reader |

If you are debugging at your own terminal you are already authorised and can
read the logs anyway, so you see the whole failure. The same shared code path
produces the safe summary for everything else, with no flag anybody can default
the wrong way.

---

## Turning them off

Individual guardrail rules can be disabled. The engine cannot be removed from
the boundary — with guardrails switched off every rule downgrades to `audit`, so
the trail still records what would have matched. That is what makes turning them
back on an informed decision rather than a hunch, and it is why the evaluation
suite's "guardrails off" run still reports what it would have caught.

```bash
export NINJASRE_MASKING_ENABLED=false
```

Masking has a real off switch, because a deployment where nothing leaves the
host has nothing to mask. Prefer `local_models_exempt` to `false` if that is
your reason: it gets the same result against a local provider and still protects
you the day somebody points a turn at a cloud one.

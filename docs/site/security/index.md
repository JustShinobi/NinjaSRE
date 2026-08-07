# Security model

Five controls. Each one is here because of a specific thing that goes wrong
without it, and each section below names that thing first — a control whose
threat nobody can state is a control nobody can evaluate, and it is usually the
first one somebody turns off.

The short version of the trust boundary: **the model is untrusted, and so is
everything it produces.** It never holds a credential, it cannot write without a
person, and everything it says passes a filter on the way out.

## The credential proxy

**The threat.** An agent that holds a credential leaks it. Not through malice —
through a prompt that asks it to print its configuration, a tool result echoed
into a transcript, an error message quoting the request it just made, or a trace
persisted to a database somebody later exports. Every one of those has happened
to somebody, and every one of them is unfixable after the fact.

**The control.** No credential exists anywhere the agent can reach: not in the
process environment, not in a prompt, not in tool arguments, not on the
filesystem, not in the trace. An integration client carries a tenant-and-team
scoped *handle*, makes its request against the proxy, and the proxy injects the
secret at the network edge — after the agent's last opportunity to observe it.

Signing schemes that need the key at request-construction time — AWS SigV4 and
its relatives — run proxy-side rather than being granted an exception. There is
no in-process-credential exception, and the absence is written down explicitly
so that "this vendor is different" is a conversation somebody has to have rather
than a patch somebody merges.

**How it is enforced.** `make check-credentials` fails the build on a credential
read outside the vault and the proxy, and on an integration reading the process
environment at all. A red-team suite asserts the credential is absent from the
prompt, the arguments, the trace, and the logs.

## Masking

**The threat.** A model provider is a third party, and production identifiers
are data your organisation may not be free to send to one. Pod names, hostnames,
cloud account identifiers, ARNs, and IP addresses are all identifying, and all
of them appear routinely in the observability data an investigation reads.

**The control.** Identifiers are replaced with stable tokens before anything
reaches a provider — `checkout-7d9f4` becomes `NSRE_MASK_POD_1` — and restored
on the way back to an authorised reader. The token carries its *kind*, because
"these two things are both pods" is most of what correlation needs and a model
can reason about that without knowing which pods.

The mapping lives on your side. A provider receives tokens, and tokens are
meaningless without the mapping, which is what makes leaving one in place the
right thing to do for a chat channel with mixed membership.

## Guardrails

**The threat.** A secret arrives in text nobody wrote — a vendor's error message
quoting an authorization header, a log line the agent read, a config dump in a
tool result. The call site cannot know what is in it, because the call site did
not write it.

**The control.** A rule engine scans at the boundary and either redacts or
refuses. It is applied at the *sink* rather than at each call site, which is the
placement that makes it unskippable: one shared code path produces full detail
for an engineer at their own terminal and the filtered version for everything
published, transmitted, or written down — including the database, because a
secret in a row is a secret in every backup and every export from then on.

Log emission goes through it too, as the last processor before the renderer.
Turning guardrails "off" means turning every action down to *audit*: nothing is
altered, nothing is blocked, and everything is still recorded. There is no
setting that removes the engine from the boundary.

Overlapping matches merge into their union rather than being redacted
independently, because independent redaction of a connection string produces
`postgres://user:[REDACTED]@[REDACTED]` — two placeholders where there should be
one, with the shape of the URL still leaking.

## Sandbox profiles

**The threat.** The agent runs code. Code that reads a file it should not, opens
a socket to somewhere it should not, or spends a machine's memory establishing
that it cannot solve the problem.

**The control.** Execution happens inside a profile that bounds CPU, memory,
wall-clock, filesystem, and network. Three profiles, matched to the three
deployment shapes:

| Profile | Isolation | Egress |
|---|---|---|
| `process` | resource limits in a subprocess | host's |
| `container` | a container per execution | container's |
| `kubernetes` | a pod per execution | Envoy sidecar, allow-listed |

Crossing a bound terminates the execution and reports *which* bound it was.
"The sandbox killed it" is not a diagnosis; "it exceeded the memory ceiling" is.

## The approval model

**The threat.** An autonomous system that can change production will, and the
change you did not want is the one you find out about afterwards.

**The control.** Read-only by default, and a capability that declares no
side-effect level is treated as a *write* rather than a read — so an omission is
safe rather than silent. Anything above read needs per-action human approval and
a stored rollback plan, and the rollback plan is shown beside the action rather
than behind a link, because a step whose undo procedure nobody read is a step
approved on the assumption that one exists.

Approval latency is a first-class metric. Gating has a cost, and a cost nobody
measures is one that gets argued about instead of managed.

## What is not defended against

Worth stating, because a security model that claims everything is one nobody
believes.

- **An operator with database access** can read the ciphertext of every stored
  credential. They cannot decrypt it without the encryption key, which is why
  the key does not live in the database — but a host with both is a host with
  the credentials.
- **A model provider you configured** receives masked text. Masking removes
  identifiers; it does not remove meaning, and the content of an incident is the
  thing being sent.
- **A malicious capability** added to the catalogue runs with the catalogue's
  privileges. The seven-artefact requirement makes one hard to add quietly; it
  does not make one impossible.

## Where nothing goes

There is no telemetry, no analytics, no crash reporting, and no version check
that transmits off-host. A CI check walks the resolved dependency tree and fails
on any package that phones home, so the property survives a library somebody
adds three levels down without reading its changelog.

When observability *is* enabled, it exports to a collector you named and nowhere
else. When something breaks, the diagnostic bundle is written to a file on your
disk, allow-listed on setting names and scanned on every value, and what happens
to it next is your decision.

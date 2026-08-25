# Backlog

Work this deployment has shown it needs, written down where the next person
looking at it will find it.

Everything here is either something that was found while building the current
release and left open, or something an operator has to do to their own
infrastructure that nobody has done yet. An item leaves this file when there is
evidence it is closed — a screen, a query, or an observed behaviour — and not
before.

---

## A team's credential and an investigation's credential resolve differently

**What happens today.** An operator connects an integration under their team,
tests it, and sees it verified against the real vendor. Every investigation then
reports that same integration unavailable.

The two resolutions are in the tree and they disagree by construction. The deep
verify runs as the caller's team: `gateway/http/routes/integrations.py` passes
the authenticated principal's team into the verifier, which uses it and falls
back to the bound one only when it is blank. Vendor tools run under the handle
`gateway/http/integration_access.py` binds at boot, and that handle is
organisation-wide, always — the composition root says so in its own docstring,
with a reason: a tool called by an investigation acts for the deployment, and a
credential written by a team-less token went to the organisation-wide handle.

**Why it is not simply a parameter.** Both sides have a defensible reading. A
team testing its own credential should test *its own* credential, or the test
proves nothing about what that team configured. An investigation triggered by an
alert has no team to act for until somebody decides that alerts belong to teams.
Making them agree means choosing which of those two is the product's answer, and
the choice reaches the credential grammar, the proxy, and what a team-scoped
credential is for at all.

**How it should be judged.** An operator stores a credential, sees it verified,
and an investigation that needs that vendor uses it. Or the screen that showed it
verified says plainly that the credential is scoped to a team and that
investigations do not run as one — but the two facts stop contradicting each
other silently.

---

## Lists in the deployment answer without asking the product

**What happens today.** Loading the incident list and the run list in the
deployed console produces **no request at all** to the service that holds them.
The service logs its own requests and there are none. Screens render, links are
drawn from data that is not the current data, and a field added to the API
appears as an empty column on a page that never asked for it.

**What has been ruled out, by measurement rather than by reasoning.** Against a
production build served locally, every way of reaching those lists — first
visit, hard reload, soft navigation, soft navigation to a route already visited
in the same session — produces a real request to the backing, every time. The
build marks every one of those routes as rendered on demand, and there is now a
check that fails the build if one is prerendered. The application's own response
carries `Cache-Control: private, no-cache, no-store, max-age=0,
must-revalidate`, which is as strict as the header gets.

**Why it is not obviously the application.** Everything the application controls
already refuses caching, and the behaviour does not reproduce without whatever
sits in front of it. The strongest remaining hypothesis is an edge layer — a
reverse proxy or a CDN in front of the console — answering from its own store
and ignoring the header. That is untested: nobody has yet compared the headers
the pod returns directly with the headers the public address returns.

**How it should be judged.** `curl -I` against the public address and against
the pod return the same caching headers, and an incident created a second ago
appears in the deployed list within one reload.

---

## The scenario corpus does not exercise the path that serves

**What happens today.** The scenario corpus runs against a harness that builds
its own loop and its own catalogue. It never calls the tool selection the
serving investigator performs, never passes through the composition root, and
never touches the remediation desk. So a change that breaks how a real
deployment selects tools can leave the corpus at a perfect score.

This was measured while wiring the two decision gates: the corpus stayed at five
of five before and after a change that altered what a real turn is offered. The
number that moved was a different one — the marked suite inside the full
verification — because a scenario written as an ordinary test is not in the
corpus by construction.

**Why it is not a matter of adding a scenario.** The corpus and the serving path
are two different loops, deliberately: the harness exists to be cheap and
reproducible, and giving it the serving investigator means giving it a
composition root, a persistence handle and a credential proxy. The honest fix is
an option — let the harness drive the serving investigator when asked — and that
is instrument work with its own design.

**How it should be judged.** Cutting a wire in the serving composition makes a
corpus run fail, rather than leaving it at five of five.

---

## A gate whose body raises does not block the call

**What happens today.** The decision gates are registered as hooks that run
before a tool call. A hook that raises is logged as a failed hook and the call
proceeds. So a gate that throws — on an unreadable posture, on a store that is
briefly unavailable, on a bug — fails **open**.

The net underneath is real and is what makes this survivable: every remediation
capability's body refuses a direct call outright, so a write that got past the
gate still reaches a refusal instead of the vendor. That refusal is the reason
the capability bodies must never be softened.

**Why it is not a one-line change.** Making a raising hook block the call
changes the behaviour of every hook in the loop, including the ones whose
failure genuinely should not stop an investigation — a recorder that cannot
write a turn should not cancel the run. What is wanted is a hook that can
declare itself load-bearing, and a loop that treats those differently.

**How it should be judged.** A gate that raises stops the call it was guarding,
and a recorder that raises does not stop the investigation.

---

## A recorded remediation does not name the approval that authorised it

**What happens today.** When an approved change executes, the approval's
identifier is written into the audit trail and carried on the execution record.
The row in the remediation ledger — the one a later proposal reads to ask "has
anything worked on this before" — has no field for it. It records that the
action was not autonomous, which is a different and weaker statement than naming
the decision that authorised it.

**Why it is not simply a column.** Adding it is a change to the persistence
model and a migration, and it is worth doing at the same time as deciding what
else that row should carry — the incident, the plan, and the approval are all
facts a reviewer wants in one place, and two of the three are there.

**How it should be judged.** Reading one row of the remediation ledger answers
"who authorised this" without joining to the audit trail.

---

## Nothing reads the signal at the moment of a change

**What happens today.** Every executed remediation writes an obligation to check
later whether it worked. The obligation is written with its "before" values
empty, because nothing on the execution path reads a live signal. The composer
passes a reader that declares it has none and logs that fact once per action, so
the gap is visible rather than silent — but the verification that runs later has
nothing to compare against.

**Why it is not a small fix.** The obligation recorder asks for the reading from
inside the unit of work it already holds. An implementation over the persistence
gateway therefore re-enters an open transaction: against the in-memory
persistence that is a deadlock, measured, and against a real database it is a
second connection taken while the first is held. What belongs there is a live
metrics source, which the composition root that builds the desk does not build.

**How it should be judged.** A remediation's recorded obligation carries the
value of the signal as it was when the change was made, and the later
verification reports a movement rather than an absence.

---

## Four capabilities above sensitive reading have no remediation components

**What happens today.** `alertmanager_acknowledge_incident`, `propose_knowledge`,
`pushover_post_message` and `telegram_post_message` declare an effect level
above sensitive reading and live outside the remediation package, so no
components are registered for them. A deployment that composes the remediation
desk therefore stops offering them to a turn — the filter is doing exactly what
it should, and the visible result is that the agent loses its notification and
knowledge-proposal capabilities.

**Why it is not a filter to loosen.** The filter's rule is the right one: a
capability the deployment cannot read, plan, apply and verify spends a schema
slot on a certain refusal. The question is which of two things is true of these
four — that they are writes and should have components, or that their declared
level is higher than what they actually do and should come down.

**How it should be judged.** A deployment with the desk composed still offers
whatever notification capability its operator expects, and no capability is
offered that would only refuse.

---

## Certificate trust can only be declared through the API

**What happens today.** A deployment can pin a fingerprint, supply a PEM, or
record an explicit accepted-unverified decision, and the refusal that happens
when none of those matches now reaches the screen with both fingerprints in it —
the observed one and the expected one. What has no screen is the declaration
itself: it is a `PUT` against the integration's trust endpoint, so an operator
reads the sentence telling them exactly what is wrong and has no field to fix it
in.

**Why it is not a text input.** The insecure form is reached by writing down
*why*, not by ticking a box, and the write is gated on a permission separate
from ordinary integration management. A form has to carry that distinction, and
the trust decision has to survive the next time somebody saves the address.

**How it should be judged.** An operator who is shown "this node presented a
certificate this deployment does not trust" can act on it from the same screen.

---

## A sub-agent's work is not traced as its own

**What happens today.** An investigation that delegates to a sub-agent keeps the
parent's trace free of the child's turns, which is the property that stops one
run's transcript absorbing another's. What does not exist is a trace for the
child. Whatever it did is not readable anywhere.

**Why it is not a matter of passing the recorder down.** A child run needs its
own identity, its own lifecycle, and a relationship to the parent that the read
path understands — otherwise the console shows two unrelated runs and nothing
says one produced the other.

**How it should be judged.** Opening a run that delegated shows what the
delegate did, as its own transcript, reachable from the parent.

---

## A resumed run does not write its outcome back to the trace

**What happens today.** Resuming a suspended run continues the work, and the
outcome of the resumed portion is not written back into the run's trace. The
module says so in its own docstring, so it is known rather than hidden, and a
reader of the trace sees a run that stopped.

**How it should be judged.** A run that was suspended and resumed reads, after
the fact, as one run that finished.

---

## One of three monitoring containers points at a resolver that no longer exists

**What happens today.** Checked from inside each of the three: the deployment's
own domain resolves from the Alertmanager container and from the Gatus
container, both against the address that preserves the caller's source IP. It
does not resolve from the Prometheus container. Which one matters more than the
count — Alertmanager is what delivers the webhook, and it resolves, which is
why delivery keeps working in spite of the third container's gap.

**Why it stays here.** It is not code in this repository. It is a change to a
container an operator owns, and nothing today asks Prometheus to reach this
deployment by name — it scrapes exporters and evaluates rules — so the gap costs
nothing until the day somebody points a receiver at this deployment from
Prometheus's own configuration, and it costs that day an afternoon instead of
five minutes.

**How it should be judged.** A name in this deployment's domain resolves from
inside all three containers, not two.

---

## The managed-secret operator in the cluster cannot authenticate

**What happens today.** The operator that synchronises secrets into the cluster
fails to authenticate, so the secrets it should manage are written by hand
instead. A hand-written secret works and then rots: it is not rotated with the
others, and nothing notices when the source of truth moves on.

**Why it stays here.** It is the operator's own cluster configuration, not this
product. What this product needs is a decision recorded either way — the
operator authenticates again, or living with hand-written secrets is a choice
somebody made on purpose.

**How it should be judged.** A managed secret resource reports itself
synchronising, or a written decision says which secrets are maintained by hand
and why.

---

## One model gateway has no key, so its provider never verifies

**What happens today.** A provider that reaches a self-hosted model gateway
cannot be verified, because no key has ever been issued for that gateway and
none is stored. The deployment runs on a different provider, so nothing is
broken — but the screen shows a provider that has never been checked, which is a
different claim from one that does not work, and neither is actionable until the
key exists.

**How it should be judged.** The provider shows as verified in the console,
having reached the gateway with a key the vault holds.

---

## An alert-raised incident's title is the alert's own name, not a sentence

**What happens today.** An incident opened from a detector shows the detector's
bare name as its title — `RestoreDrillStale`, `ProxmoxGuestStopped` — never a
sentence, in every incident this deployment has raised. This is not an
accident of rendering: the title is set to `detector.name` at the moment the
incident is raised, and the choice is a deliberate, documented one — a title
that has to stay readable for an incident naming one resource has to stay
readable for the same incident naming fifty, and a name is what does that.

The gap is not that no sentence exists. The investigation attached to the same
incident writes one, correctly, every time — "The weekly restore drill cron
jobs on node pve02 exceeded their maximum scheduled execution window without
completing successfully" sits one screen away from the incident whose title
still reads `RestoreDrillStale`. The product produces the sentence this wave
exists to surface everywhere an identifier used to be, and then does not carry
it up to the one field a list of incidents is read by.

**Why it is not simply reading the investigation's headline back.** An
incident can outlive several investigations — this deployment watched one
incident absorb the same alert seven times over six and a half hours, each
delivery producing its own investigation — and a title sourced from "the last
investigation's headline" would rewrite itself out from under an operator
mid-read, and would be blank for the entire window between an incident opening
and its first investigation concluding. The detector's name is stable for the
whole of an incident's life for a reason; a sentence would need its own
lifecycle to be that reliable, not a straight substitution.

**How it should be judged.** An incident's title, read at any point in its
life including before an investigation concludes, is a sentence a person can
act on without opening anything else — not the identifier a detector happens
to be named.

---

## An incident can be recorded against the host that scraped it

**What happens today.** The header under an incident's title shows the host of
the resource the incident's first subject resolves to
(`console/src/surfaces/screens/incident-detail.tsx`: the resource is fetched by
the incident's own `subjects[0]`, and its `kind`/`display_name` become the
"node" text). For an alert whose own metric is scraped by the resource it is
about — a node's own `node-exporter` — that resolution lands correctly, because
the two coincide. For an alert whose metric was scraped by one exporter on
behalf of every guest in the cluster — Proxmox's own guest-power metric, read
from `pve-exporter`, which runs on one node and describes all of them — the
same resolution lands on the exporter's own host, not on the guest the alert is
actually about. A guest stopped on `pve01`, reported through an exporter
running on `pve02`, opens an incident whose header reads `node pve02`, three
lines above the alert's own labels correctly saying `node=pve01` — and the
investigation attached to the same incident, on the very next screen, also
says `pve01`, correctly. The product has the right answer in two other places
on the same incident and puts the wrong one in the header a person reads first.

**Where the defect actually is, read from the database rather than the screen.**
The header is not misreading a label. The subject the incident *stores* is the
wrong resource. Asked directly what the incident points at, the record answers:

    resource_id   res-47555daca81efa67dacce16fb42c898e
    kind          node
    native_id     node/HAL9000/pve02
    display_name  pve02

for an incident about a stopped guest on a different node. The correlation that
opened it recorded how it matched — by address, against the label naming the
scraping instance — and that address belongs to the exporter's host. Every
screen downstream is rendering that stored subject faithfully. **The fix belongs
to the correlation at intake, not to the header component**, and an entry that
sends someone to the header sends them to the one place where nothing is wrong.

*Two earlier readings of this were wrong and are recorded as wrong, because the
sequence is itself worth knowing. The first blamed a guest's stored identity for
carrying a literal `unknown` where its node should be — but a guest's identity
is `kind/cluster/creation-discriminator/vmid` by explicit design
(`integrations/proxmox/identity.py`), the node is deliberately excluded so that
a migration does not restart a guest's history, and `unknown` is the fallback
for a missing creation timestamp. The second blamed the header's own resolution.
Only reading the stored row settled it.*

**Why it is not simply reading a different label.** The header cannot switch to
"whichever label looks like a node" without knowing, per alert source, which
label names the scraping exporter and which (if any) names the actual subject —
that knowledge is exactly what a per-source correlation rule is for, and a
guest-level alert sourced from a cluster-wide exporter needs a rule that
resolves to the guest, not to whatever host happened to answer the scrape.

**How it should be judged.** An incident opened from an alert whose exporter is
not local to its subject **stores** the subject the alert is about, and every
screen that reads that stored subject then agrees with the alert's own labels
and with the investigation — which today are the two places that already have
it right.

---

## A run's cost is reported two different ways on two different screens

**What happens today.** The same completed run shows `Not recorded` for its
cost on the incident's own panel, and a real per-turn dollar-and-token
breakdown on the run's own detail screen. Both describe the same run, read
moments apart.

**How it should be judged.** The incident panel and the run's own screen agree
on whether a run's cost was recorded, and when it was, on what it was.

---

## A deployment has been watched acting on its own diagnosis once, and stopped short of the last three steps

**What happens today.** A container that was both disposable and covered by an
alert rule was stopped by hand, once, in a combined window with an operator
present. The alert fired on its own within the rule's `for` window; the webhook
accepted an authenticated delivery; an incident opened; an investigation ran and
recorded its turns, its calls, and what each call returned — including two
honest, verbatim upstream failures rather than an invented negative; the report
rendered as a sentence naming the correct host; and the incident closed itself
when the underlying condition cleared, recording that a human restarted the
container rather than claiming the product had. All of that is read back from
storage, not from the process that produced it.

What did not happen is the last three steps: propose, approve, execute. Not
because nothing was watched, and not because the approval machinery is missing —
the gate, the audit trail, and the decision-recording order are all composed and
reachable, and the hypervisor token carries power-management rights, checked
against the vendor's own access log and ACLs rather than assumed.

**The capability that would have fixed it exists, and was cut from the offer by
the language the alert was written in.** The catalogue holds twenty-four
capabilities above read level, twenty of them remediation, and one of them starts
a stopped guest. The turn was offered forty tools out of sixty candidates. The
selector orders candidates by term overlap between the incident's own summary and
each capability's declared use cases — and those use cases are written in
English, while the alert's description was written in the operator's language.
Scored with the product's own scorer, one sentence, two languages:

    "…estava em execucao no no pve01 e parou."   start-guest  0.0000  →  63rd, cut
    "…was running on node pve01 and has stopped." start-guest  0.7407  →  13th, offered

One variable. The deployment was offered seven ways to stop, shut down, suspend,
reboot, resume, migrate and relocate a guest, and not the one that starts it, in
an incident about a guest that had stopped. **The agent was right not to propose
anything — it had nothing to propose with.**

When every candidate scores zero, the tie breaks by name, so which forty tools a
turn receives comes down to alphabetical position. The product does not refuse
and does not warn: it hands over forty tools chosen by the alphabet and proceeds
as though it had chosen them.

*An earlier reading of this said the catalogue held three capabilities above read
level, all notifications, and that nothing anywhere could act on infrastructure.
That was wrong, and it was wrong twice before the instrumentation that this same
work produced made the real answer reachable: the run's own record now states
`ranked 60, offered 40, cut by the ceiling 20` and names each candidate with its
score.*

**Why it is not just a matter of trying again.** Trying the same window again
with the alert unchanged reproduces the same outcome, because the outcome follows
from how candidates are scored rather than from what happened that night. The
alert's own description has since been rewritten in English, which is enough to
put the starting capability back inside the offer — so the window is worth
running again. But that is a workaround applied to one alert, not a fix: the next
alert somebody writes in their own language scores every capability at zero
again, silently.

**How it should be judged.** The same shape of run — a disposable, alerted
resource stopped by hand, diagnosed correctly — produces a proposal with a
rollback plan, waiting on `/decisions`; a person approves it; the resource
comes back through the gate rather than by hand; and the outcome, the episode,
and the incident's own timeline all say so.

---

## Which tools a turn is offered depends on the language its incident was written in

**What happens today.** Before each turn, the deployment narrows the catalogue
to what the team has connected and what it can carry, ranks what survives, and
cuts at a ceiling. The ranking scores each candidate partly by how many terms
its declared use cases share with the incident's own summary. Those use cases
are written in English throughout the catalogue, the tokeniser keeps runs of
`[a-z0-9_]+`, and the stop-word list it filters against is twenty-six English
words. An incident summarised in any other language shares no terms with
anything, so **every candidate scores zero on that component at once**.

A tie at zero is broken by name. So a deployment whose alerts are written in the
operator's own language does not get a slightly worse ranking — it gets the
alphabet, and the forty tools a turn receives are the first forty by name. This
is not a hypothetical: it happened on the first attempt, to the operator of this
deployment, writing an alert in the language they speak.

**Why it is not simply translating the summary.** Translating on the way in
would put a machine translation between the operator's words and the record of
what the agent was told, which is the opposite of what a transcript is for. And
scoring is not the only thing that reads the summary. The narrower question —
should overlap be measured on something language-independent, or should the
scorer refuse to rank when it can find no signal at all rather than falling
through to alphabetical order — is a design decision, not a patch.

**What makes it hard to notice.** The product does not refuse, does not warn,
and does not score differently from a legitimate tie. It hands over forty tools
and proceeds as though it had chosen them. Nothing in the code says the
selection is language-dependent — not a docstring, not a constant, not a test.
The record that finally showed it (`ranked 60, offered 40, cut by the ceiling
20`, with each candidate's score) exists only because a separate piece of work
added it while trying to answer why a particular investigation had proposed
nothing.

**How it should be judged.** An incident written in a language the catalogue was
not authored in either ranks capabilities on a signal that survives the language
difference, or says out loud that it could not rank them — and in no case
silently substitutes alphabetical order for a decision.

---

## No observation an investigation records is ever marked as cited

**What happens today.** Investigations write observations to the evidence store,
from real sources — logs, metrics, hypervisor configuration and events, change
history, the alert itself, and the agent's own reasoning. Each row carries a flag
saying whether the finished report actually cited it. Across every row in this
deployment, that flag is false. Not mostly false: false without exception.

Two readings are possible and the data does not separate them. Either nothing
ever writes the flag, in which case the column is decoration; or reports
genuinely cite nothing they recorded, in which case the evidence trail and the
conclusion are unconnected. Both are worth knowing and they have different
fixes.

**The second number that comes with it.** Of the runs that recorded turns, only a
small minority recorded any observation at all — including the one run this
deployment has been watched closing a loop with, which recorded five turns, four
tool calls, and zero observations. So "which evidence supported this conclusion"
is a question the store usually cannot answer, separately from the flag.

**Why it is not a one-line fix.** Marking a row cited requires knowing which
observation a sentence in the report came from, and that link is not currently
carried anywhere between the reasoning that produced the sentence and the row
that was written. Deciding where it is carried is the work.

**How it should be judged.** A finished investigation names the observations its
conclusion rests on, those rows are marked as cited, and a run that cites nothing
is visibly a run that cited nothing rather than indistinguishable from every
other run.

---

## The interface rules can pass against a page that is not the application

**What happens today.** A suite of transversal rules sweeps the product's main
screens and asserts things like "no screen prints a raw report as text". Run
against a live deployment, its session can end mid-run. When that happens the
browser lands on the sign-in page, and the rules keep running: a rule looking for
raw markdown finds none, because there is no screen there at all, and **reports a
pass**.

It was caught by accident, from file sizes: five captures of five different
routes, all exactly the same number of bytes, against a hundred-and-seventy
kilobytes to two-and-a-half megabytes on a healthy run. Four rules had passed
while photographing a login form. A rerun in the same conditions was green
throughout, so nothing about the product was wrong — but nothing about the run
said which of the two it had been either.

**Why it matters more than an ordinary flake.** These rules are the scoreboard
that says whether the interface still obeys the product's own conventions. A
flake that fails is noise. A flake that *passes* removes the only thing standing
between a regression and a release, and does it silently.

**How it should be judged.** A sweep that is not looking at a signed-in
application fails, loudly, naming what it found instead — and no rule in the
suite can report a pass from a page it was never meant to be on.

---

## The gate that checks routes are dynamic cannot tell whether they declare it

**What happens today.** Every screen route under the console shell must reach
the deployment on each request rather than be served from a page baked at build
time, and a gate exists to enforce that. It reads the build's own output and
fails if any shell route was pre-rendered.

It passes today, and it would pass just as green if every route stopped
declaring anything at all. The property is held up by three independent
mechanisms — a declaration on the shared layout, a prop that thirty-four of the
thirty-six pages happen to take, and an unconditional cookie read in the layout's
authentication — and any one of them alone is enough to make the build dynamic.
Cutting the first and rebuilding was measured: still green, with no declaration
anywhere under the shell.

**Why that is worth an entry rather than a shrug.** The gate was written against
a specific failure — a layout whose dynamism silently stops applying to a child
segment — and that is exactly the failure it cannot see, because it inspects the
result rather than the declaration. The routes now each declare their own
dynamism, which is the right fix and the durable one; but nothing stops the next
refactor from removing thirty-six declarations without a single test going red.

**Why it is not simply grepping for the declaration.** A grep would pass on a
declaration inside a comment, and would fail on a route that is legitimately
dynamic by another declared means. Deciding what counts as a per-file
declaration, and which routes are required to carry one, is the work — and the
answer has to survive the framework changing how it infers dynamism.

**How it should be judged.** Removing the per-route declaration from one shell
route turns the gate red, naming that route, whether or not the build happens to
come out dynamic anyway.

---

## A credential refused for travelling in clear text is explained as a host problem

**What happens today.** The credential proxy refuses to send a stored secret
over an unencrypted connection, and the refusal carries a sentence of its own
saying so and offering both ways out — use TLS, or make the call without the
credential. That sentence never reaches the operator.

Every vendor's verifier keeps a table of advice per failure reason, and both
refusals — a host outside the declared allow-list, and a credential that would
cross in clear — are classified alike, deliberately: by every fact the proxy
checks, the second *is* an egress refusal. The tables were written when the
allow-list case was the only one that classification covered, so the panel now
answers a scheme problem with

    The proxy refused the call before it left: this host is not in the
    integration's declared allow-list.

The host is in the allow-list. The operator is sent to check the one thing that
is correct, and told nothing about the `http://` that actually stopped the call.
Fifteen vendors carry the same table and the same sentence.

**How it was found.** By writing the acceptance test that had been marked done
but never written — pointing a vendor at `http://` over the compose backing and
reading the panel. Two claims were on trial: the state chip, which turned out
correct and unchanged; and the sentence, which turned out to be somebody else's.

**Why it is not a one-line edit.** The two causes are indistinguishable by
classification *on purpose*, so telling them apart in the advice table means
either giving the clear-text refusal its own reason — which changes a shared
enumeration and every consumer of it — or dropping the per-vendor advice for
this class and falling back to the refusal's own sentence, which is already
complete for both cases. The second is smaller and probably right, but it
removes vendor-specific wording an operator may be relying on, across fifteen
packages at once. That is a product decision, not a cleanup.

**How it should be judged.** A credential refused for the scheme it would travel
over says so on the screen, names the scheme, and offers the same two ways out
the refusal already carries — and a credential refused for its host still says
that instead.

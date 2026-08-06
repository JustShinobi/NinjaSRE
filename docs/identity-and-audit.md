# Identity, access, and the audit trail

Who is acting, what they may do, and the record of what they did. This is the
operator's guide: the role model, connecting an identity provider, machine
tokens, the break-glass procedure, and getting the audit trail out.

## The shape of it

Three kinds of principal reach NinjaSRE, and they authenticate differently.

| Principal | How it authenticates | Bounded by |
|---|---|---|
| A person | OIDC against your provider, Authorization Code with PKCE | an idle timeout and an absolute session lifetime |
| A machine client | a scoped bearer token | its team, its permission set, and its expiry |
| The local administrator | a passphrase held by this deployment | fifteen minutes, and a prominent audit trail |

Every privileged action any of them takes is attributable to a principal and
recorded in a log nothing can edit.

## Roles

Five roles, and they nest: each holds everything the one below it holds and
more. Two overlapping-but-incomparable roles is one more mental model than
anybody holds during an incident, and nesting means a denial always has the same
answer — "you need the next role up".

| Role | What it adds |
|---|---|
| `viewer` | reads investigations, reports, memory, knowledge, configuration, and pending approvals |
| `responder` | runs investigations, approves and executes remediation, reviews approvals, writes knowledge |
| `operator` | writes configuration, manages credentials, integrations, and schedules |
| `admin` | manages people, tokens, SSO, and impersonation; reads and exports the audit trail |
| `owner` | deletes the organisation, and appoints other owners |

A role is not held globally — it is **granted at a node** of the configuration
hierarchy, and it applies to that node and everything beneath it. A grant at
`payments` covers `payments/checkout`; it does not cover `platform`, and it does
not cover the organisation above it. Inheritance runs downward only.

If somebody needs a narrow permission — read configuration everywhere, approve
remediation on one team — give them the lower role organisation-wide and the
higher role at the node. That is what node scoping is for, and it is why there
is no sixth role for every combination.

### An organisation always has an owner

Any change that would leave an organisation with no `owner` is refused, however
it is phrased: removing the last owner, demoting yourself, or removing every
owner in one call. Handing ownership over in a single operation — granting the
replacement and removing yourself at once — is allowed, because the check looks
at the whole change rather than at each removal.

### When a request is refused

A denial names the permission, the scope, and the cheapest role that would have
granted it:

> This action needs `'config.write'` at `'payments'`. The `'operator'` role grants it.

That is deliberate. A denial nobody can act on is a denial they route around.

## Connecting your identity provider

NinjaSRE speaks OIDC Authorization Code with PKCE against a provider you run or
subscribe to. It never talks to an identity service of ours, because there is
not one.

**1. Register NinjaSRE as an application** in your provider. Set the redirect
URI to `https://<your-host>/auth/callback`. Request the `openid`, `profile`,
`email`, and `groups` scopes.

**2. Configure the provider** with the issuer, client id, authorisation
endpoint, token endpoint, and JWKS URI. All four must be `https` — a
configuration with a plaintext endpoint is refused rather than warned about.

**3. Map groups to teams.** Group names come from your directory; node ids come
from your configuration hierarchy. A user in several mapped groups lands in the
first one their provider returned, which matches how directories order group
membership.

**4. Set a default team.** This is required, not optional. A provider that
returns no group claims — because a user is in no groups, or because the claim
was not released for them — maps to the default and the fallback is recorded in
the audit trail. The alternative is refusing the sign-in, which turns a
directory change nobody made deliberately into an outage.

**5. Test before activating.** This is enforced: a configuration that has not
completed a test sign-in cannot be activated. The test result is bound to the
exact settings that produced it, so editing anything — the client id, the group
map, the claim names — invalidates it and the test has to be run again.

A misconfigured provider is not a degraded feature. It is every human locked out
of the tool they would use to fix whatever prompted the change.

### Group membership is re-read at every sign-in

Nothing about a user's team survives from their last session. Removing somebody
from a group in your directory takes effect the next time they sign in, not
whenever a cache expires.

### Sessions

A session ends when either bound is crossed: **thirty minutes idle**, or
**twelve hours** from sign-in, whichever comes first. Activity pushes the first
out and never the second. Signing out withdraws the session immediately, and so
does revoking a principal's sessions from the admin surface.

One person may hold several sessions at once — the console, the CLI, a chat
surface — and they are independent. Revoking one leaves the others alone;
revoking the principal withdraws all of them.

## Machine tokens

A token carries an organisation, a team, a permission set, an expiry, and a
description. It is a credential in its own right: it can hold *less* than its
owner does, and never more. A token narrowed to `investigation.run` stays
narrowed even if its owner is promoted to `admin` tomorrow.

**The value is shown once.** It is stored as a keyed hash, and there is no code
path that returns it again — a lost token is re-issued, not recovered.

**Every token expires.** Ninety days by default, a year at most. There is no
"never expires": a token nobody remembers issuing is the one still working after
the person who created it has left.

**Tokens are revoked immediately.** Revocation takes effect on the very next
request. There is no cache window to wait out.

Three policies run on their own:

- a token unused for **sixty days** is revoked automatically, and its owner is
  told which one and why;
- a token within **fourteen days** of expiry produces a warning, so renewing it
  is routine rather than an incident;
- **bulk revocation** covers a team, an owner, or an explicit list, for when
  incident response needs a lot of credentials gone at once. It is bounded at
  500 per call, because one statement that could revoke a whole deployment is
  not a control.

A token whose team has been deleted is rejected with a reason that says so.
Re-issuing will not fix it; the team has to exist.

## Impersonation

An admin can act in a team's context to reproduce what that team is seeing.

- It requires `impersonation.use` **at that node** — an admin scoped to one
  division cannot support a team in another.
- It lasts at most **one hour**, and expires by itself.
- It requires a stated reason, and refuses to start without one.
- Every action taken under it records **both** principals: the real human, and
  the context they were acting in. Starting and ending an impersonation are
  audited separately from the actions taken during it, so "when did this person
  have that access" is answerable without inferring it from side effects.

## Break-glass

A local administrator account exists for two situations: bootstrapping a new
deployment, and getting in when the identity provider is unreachable.

It is a deliberate trade. An SSO outage that locks you out of your own incident
response tool during an incident is a worse failure than a local account being a
standing target — so the account exists, and everything about it is arranged to
make abuse expensive and detection cheap.

**The procedure.**

1. `POST /auth/break-glass` with the passphrase and a written reason. The
   reason is required and must be at least a sentence; it goes on the audit
   record, and it is what somebody reads six months later.
2. You get a session lasting **fifteen minutes** — shorter than an ordinary
   session and shorter than an impersonation, because it should expire before
   the outage does.
3. Every action in that session is flagged as break-glass in the audit trail,
   and the sign-in itself is logged at error level. A break-glass sign-in that
   nobody noticed is the one that was not an emergency.
4. Fix the thing. Sign out.

The account holds `owner` over the organisation, which is what lets it repair
the second situation: an organisation whose last owner lost access.

**Operating it.** Store the passphrase where you store your other break-glass
credentials — a sealed envelope, a password manager with a separate approval
path, whatever your process already is. Disable the account entirely if your
deployment has no use for it; a deployment with it disabled has no account to
attack. Rotate it when somebody who knew it leaves.

## The audit trail

Every privileged action is recorded with the principal, the impersonation
context if there was one, the timestamp, the action, the target, the outcome,
and the source address.

**Nothing can change a record.** Three layers, and the third is the one that
matters:

1. the storage interface has no update and no delete — there is no method to
   call;
2. a startup check fails the process if any repository grows one;
3. a database trigger rejects `UPDATE`, `DELETE`, and `TRUNCATE` on the audit
   table, whoever issues them and however.

An audit log an administrator can edit is not evidence. The trigger is what
survives a refactor, an ORM, and a `psql` prompt.

**Audit records are exempt from retention.** Every other class of record has a
window after which it is swept; this one has none, and a retention policy that
would delete audit records cannot even be constructed.

**If a write fails, it is a serious error.** The action being audited has
usually already happened, so proceeding quietly is the one outcome that is not
acceptable. Instead the record goes to a durable file, an alert is raised, and
the caller is told the trail is incomplete. Point the file somewhere you back up
with `NINJASRE_AUDIT_FALLBACK_PATH`.

### Getting it out

The trail only grows, so exporting it is how you bound that. `GET /audit/export`
streams newline-delimited JSON — one flat object per record,
`application/x-ndjson`:

```json
{"action":"config.field.set","actor_id":"ada","actor_kind":"user","detail":{"field":"policies.masking.level","real_principal_id":"ada","source_address":"203.0.113.7"},"event_id":"…","occurred_at":"2026-08-06T12:00:00+00:00","org_id":"acme","outcome":"allowed","resource_id":"payments","resource_kind":"config_node"}
```

Splunk, Elastic, Loki, and a shell pipeline all ingest it as it stands. A
truncated file is still valid up to its last newline, and the export streams
rather than materialising the window, so a month of history does not have to fit
in memory.

The durable fallback file uses the same record shape, so what you recover after
an outage merges with what you exported before it.

Take a window with `since` and `until`, archive it, and keep going. Nothing is
deleted at this end — that is the point.

## Attribution inside an investigation

An investigation carries the principal that caused it, so every capability it
executes is attributable. It rides on the run's team context, which every stage
already holds and which the trace serialises whole — a resumed session keeps it,
and no stage has to remember to write it down.

A run nothing human started — a scheduled sweep, a replayed fixture — records no
principal, and says so rather than naming one. That distinction is visible in
the trace and is the honest one.

## What is audited

At minimum: authentication, token lifecycle, configuration changes, credential
changes, approvals, remediation execution, impersonation, permission and role
changes, and break-glass use.

Every one of those carries both principals when an impersonation is in force. It
is asserted across the whole vocabulary rather than a sample, because a
dual-principal trail with one gap is a trail somebody can act through.

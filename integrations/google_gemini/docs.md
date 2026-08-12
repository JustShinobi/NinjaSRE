# Google Gemini

A language-model provider, declared as an integration so its key is reachable
through the credential proxy rather than only through the process environment.

## Why this exists

A provider key could be stored and never read. The vault held it, the vault's
`reveal` belongs to the credential proxy alone, and the proxy had no rule for
any language-model provider — so the key went in and stopped there, while the
model client read an environment variable. Article IV says a credential must not
be in the agent's process environment; the most sensitive credential in the
system was the one living there.

## What to configure

One field.

| Field | What it is |
|---|---|
| `api_key` | The key from Google AI Studio. Sent as `x-goog-api-key` on every request. |

The key is never sent in the query string, which Gemini also accepts. A query
string reaches access logs, proxy logs and referrer headers, and a key that has
been written to a log has to be rotated.

## Where to get it

Google AI Studio issues the key. The project it belongs to needs the Generative
Language API enabled and, past the free tier, billing attached — a key from a
project with the API switched off authenticates and then refuses every call,
which reads as a bad key and is not one.

## Egress

One host: `generativelanguage.googleapis.com`. Exact, not a suffix match. The
allow-list is what stops a compromised prompt sending the key somewhere else.

## What it does not do

It does not carry inference. Investigations reach models through the model
layer's own adapters; this integration exists so the *credential* is routed the
way every other credential is, and so an operator can verify a stored key works
before an investigation depends on it.

---
name: model-provider-google-gemini
display_name: Google Gemini key and models
description: Whether this deployment's provider key can call the model it is configured for, which is the failure a refusal naming a model hides behind one naming the key.
domain: model_provider
applies_when:
  alert_sources: []
  tags: [model_provider, credentials, gemini]
directs_tools:
  - google_gemini_available_models
requires:
  integrations: [google_gemini]
---

# Investigating with Google Gemini

This integration answers one question, and it is a question about the
deployment rather than about the estate: **can this key call the model we are
configured for?**

## When to reach for it

When a provider refusal names a model rather than the key. Those are different
failures with the same symptom — an investigation that will not start — and only
the provider can tell them apart:

- the key is wrong, revoked, or from a project with the API disabled;
- the key is fine and is not allowed to call the model this deployment names.

The second is invisible from inside NinjaSRE. The model listing answers it
directly.

## How to read the answer

The result is the set of models the key may call, and nothing else. Compare it
with the model this deployment is configured for:

- **the configured model is in the list** — the key is not why the investigation
  failed, and the cause is downstream;
- **the list is non-empty and the configured model is absent** — the
  configuration names a model this key cannot reach; that is the finding;
- **the call itself failed** — the key or the project is the problem, and the
  verification report says which.

## What it will not tell you

Anything about quota, cost, or latency. A key that may call a model can still be
rate-limited, and a listing that succeeds says nothing about whether the next
inference will. Read the provider refusal for that, not this.

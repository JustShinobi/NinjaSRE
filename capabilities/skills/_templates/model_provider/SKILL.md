---
name: model-provider-VENDOR
display_name: VENDOR provider diagnosis
description: Whether the deployment's own model provider is the failure, before anything else is blamed.
domain: model_provider
applies_when:
  tags: [model_provider, llm, quota, authentication]
directs_tools:
  - VENDOR_available_models
requires:
  integrations: [VENDOR]
---

# VENDOR provider diagnosis

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Separate the key from the model.** A refusal naming a model often hides
   one naming the key: list what the credential can actually reach before
   concluding anything about the model chosen.
2. **Check the configured model is on the list.** A deployment configured for
   a model the provider no longer serves fails on every call with an error
   that reads like an outage.
3. **Read the refusal's own vocabulary.** Quota, rate limit, authentication
   and safety refusals are four different remedies wearing similar words.
4. **Only then look at the request.** A prompt-shaped failure — context
   length, tool schema — is the last hypothesis, because it is the only one
   the other three checks cannot produce.

## What a finding must carry

- Which credential was exercised, by name — never its value.
- The model asked for, and whether the provider lists it.
- The provider's own error text, quoted, not paraphrased.

## What this is not for

- Diagnosing the workload the model was asked about — that is the estate's
  own skill; this one only decides whether the provider is the problem.
- Choosing a model. It reports what the credential can reach; the choice is
  configuration, made by a person on the first-run screen.
- Anything that would send the credential's value anywhere, including into
  a finding.

# How an integration authenticates

Every integration in NinjaSRE reaches its vendor through the credential proxy.
The client carries a tenant-and-team-scoped handle; the proxy resolves it
against the encrypted vault and injects the real secret at the network edge. No
integration holds a credential, and there is no configuration under which one
can.

This document records how each vendor gets there, because vendors differ in ways
that matter and the differences have to be decided per vendor rather than argued
about per pull request.

## The four rows, and the one that is not a row

| Situation | Approach | Strategy |
|---|---|---|
| The SDK accepts a custom transport or base URL | Point it at the proxy | `routed_sdk` |
| The SDK signs internally with an in-process key | The client sends an unsigned request; the proxy signs it | `proxy_signed` |
| The SDK is thin over REST | Replace it with a direct client on `integrations/_base/client.py` | `direct_client` |
| The SDK is essential and uncooperative | **Not accepted.** | `no_exception_granted` |

The fourth row is written down so that the absence is explicit rather than
implied. `SdkStrategy.NO_EXCEPTION_GRANTED` exists as a name and an
`IntegrationDescriptor` that declares it raises at construction — there is no
in-process-credential exception, and a vendor library that insists on loading
its own key is replaced rather than accommodated.

## What each integration declares

An integration's `DESCRIPTOR` carries four things, and a contract suite walks
the package tree asserting that every installed vendor has all of them:

- **the credential schema** — field names, types, and validation, checked on
  write so a mistyped key is rejected while somebody is still looking at the
  screen;
- **the injection rule** — how the secret enters the request, and the hosts the
  integration may reach, which are the same tuple because two lists would drift;
- **the verifier** — one cheap read-only call that proves the credential works,
  so an operator can check a credential without being shown it;
- **the SDK strategy and its rationale** — a row above, and why.

## The reference integration

### Kubernetes — `direct_client`

A bearer token, and the case where NinjaSRE cannot know the allow-list. Every
deployment's API server is somewhere else, so `schema.rule_for(...)` builds the
rule from the endpoints an operator actually configured. The in-cluster address
is always included, because a deployment with an external endpoint may still run
workers inside the cluster and discovering that during an incident is not the
moment to find out the list is one entry short.

The official client's transport can be replaced; its credential loading cannot.
It reads a kubeconfig or an in-cluster service account token itself, which is
the one thing about it that is not configurable and exactly the behaviour
Article IV forbids. `tests/contract/integrations/test_reference_integrations.py`
is what pins this: an operator-declared allow-list is permitted, and nothing
else is, in-cluster access included.

A vendor whose SDK signs requests internally with an in-process key — the
`proxy_signed` row of the table above — has no exemplar in the catalogue
right now: the strategy is one this codebase supports and enforces
(`platform/credentials/proxy/signing/`, unit-tested on its own), not one a
currently embarked vendor happens to use.

## Adding an integration

One package under `integrations/<vendor>/`, exposing `DESCRIPTOR`. Discovery
walks the tree, so there is no registry to register with — which is the property
that keeps a growing catalogue addable one package at a time. An
integration that forgets its descriptor, whose client does not sit on
`IntegrationClient`, or whose schema and injection rule have drifted apart fails
the contract suite the day it lands.

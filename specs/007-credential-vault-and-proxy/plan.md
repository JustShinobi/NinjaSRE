# Plan — 007 Credential Vault and Proxy

## Summary

Build an encrypted, versioned credential vault behind `CredentialStore`, and a
proxy that is the only component in the system able to read a secret. Provide the
integration base client that makes the proxy path the only path, and enforce it
with a CI check and a red-team test.

## Technical context

| Aspect | Choice |
|---|---|
| Storage | `CredentialStore` port over encrypted Postgres columns (feature 006) |
| Encryption | AES-GCM with a key from operator configuration; envelope encryption ready for a KMS backend |
| Proxy transport | HTTP forward proxy with an internal API; `httpx` on both sides |
| Injection | Declarative `InjectionRule` per integration, applied at the edge |
| Signing | Proxy-side SigV4 and vendor-equivalent signers |
| Dev mode | Same proxy code mounted as an in-process ASGI app — one implementation, two mount points |
| Audit | `AuditRepository` (feature 006) |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | Every resolution audited (FR-019); capability errors are structured evidence |
| II | Rate limits, timeouts, and refresh windows are named constants |
| III | The proxy enforces the egress allow-list, bounding what a capability can reach even before approval |
| IV | **This is the feature.** FR-001 to FR-021, SC-001 |
| V | Runtime-agnostic |
| VI | Provider credentials also resolve here, so no LLM key sits in the agent process either |
| VII | N/A |
| VIII | `platform/credentials/` tier 3; `integrations/_base/` tier 2 |
| IX | The base client is what every capability's external call funnels through |
| X | Nothing leaves except to the vendor the operator configured, via the allow-list |
| XI | Storage via `CredentialStore` only |
| XII | The red-team test (SC-001) is written before the proxy |
| XIII | Provenance headers |

**Violations:** none.

## Project structure

```
platform/credentials/
├── vault.py                  # encrypted, versioned storage over CredentialStore
├── schemas.py                # per-integration credential schemas + validation
├── proxy/
│   ├── app.py                # ASGI app — mounted in-process or served standalone
│   ├── resolution.py         # handle → tenant/team → credential
│   ├── injection.py          # header, query, path, body, basic, bearer
│   ├── signing/
│   │   ├── sigv4.py
│   │   └── vendor.py         # other signing schemes
│   ├── egress.py             # per-integration allow-list enforcement
│   ├── refresh.py            # OAuth/STS refresh with one retry on expiry
│   ├── rate_limit.py
│   └── audit.py
├── verification.py           # end-to-end credential check
└── health.py

integrations/_base/
├── client.py                 # the only sanctioned authenticated-call path
├── errors.py                 # structured integration errors
├── pagination.py
└── retry.py

tools/check_direct_credentials.py   # CI enforcement
tests/security/test_no_credentials_in_agent.py   # SC-001 red team
```

## Injection rule model

Declared per integration, never coded ad hoc:

```python
InjectionRule(
    integration="datadog",
    hosts=("api.datadoghq.com", "api.us5.datadoghq.com", "api.datadoghq.eu"),
    injections=(
        HeaderInjection(header="DD-API-KEY", field="api_key"),
        HeaderInjection(header="DD-APPLICATION-KEY", field="app_key"),
    ),
)
```

`hosts` doubles as the egress allow-list (FR-009). An integration may not reach a
host it did not declare.

## Vendor SDK strategy (FR-018)

| Situation | Approach |
|---|---|
| SDK accepts a custom HTTP transport or base URL | Route through the proxy; preferred |
| SDK signs internally with an in-process key (AWS, GCP) | Proxy-side signing; the client sends an unsigned request with a handle |
| SDK is thin over REST | Replace with a direct client on `integrations/_base/client.py` |
| SDK is essential and uncooperative | Not accepted. There is no in-process-credential exception. |

Each integration's docs record which row applies.

## Implementation phases

### Phase 1 — Red team first
Write `tests/security/test_no_credentials_in_agent.py` (SC-001) and the CI check
violation fixture (SC-003). Both red. Everything else exists to make them pass.

### Phase 2 — Vault
Encrypted versioned storage, per-integration schemas, validation on write,
metadata-only read API (FR-003).

### Phase 3 — Proxy core
ASGI app, handle resolution, header/query/path/body/basic/bearer injection, egress
allow-list, structured resolution errors.

### Phase 4 — Signing and refresh
SigV4 and vendor signers, OAuth/STS refresh with the single expiry retry.

### Phase 5 — Base client
`integrations/_base/client.py` with retry, pagination, timeout, rate-limit
handling, structured errors, proxy routing. Two reference integrations built on it.

### Phase 6 — Enforcement
`check_direct_credentials.py` wired into `make verify`; catalogue-wide test that
every integration routes through the proxy (SC-002); no-fallback test (SC-005).

### Phase 7 — Operations
Audit, rate limiting, health, verification command, rotation without restart
(SC-004), per-team isolation (SC-007), dev in-process mount (FR-011).

## Complexity tracking

| Item | Justification |
|---|---|
| Mandatory even in development | ADR 0005. A production-only proxy means every line of code is written and tested against a path that does not exist in production. The in-process mount makes the dev cost roughly zero. |
| Proxy-side request signing | Signing requires the key. Keeping SigV4 in the client would mean AWS — the most-used integration family — is the one exception to the whole invariant, which makes the invariant worthless. |
| No bypass under any configuration | A bypass flag is the thing that gets set during an outage and never unset. Availability is solved by co-locating the proxy (feature 030), not by a fallback. |
| Rewriting uncooperative vendor SDKs as direct clients | Costly per vendor, but the alternative is a credential in the agent process, which is the failure this feature exists to prevent. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Swapnil | Credential proxy concept and skill-side contract (`get_config()` reading tenant/team, never secrets) | ADOPT → elevated from production mode to constitutional invariant |
| Swapnil | `sre-agent/sandbox-router/sandbox_router.py` routing | ADAPT → `proxy/app.py` |
| Swapnil | `config_service/src/crypto/` | ADOPT (via feature 006) |
| Swapnil | `config_service/src/core/integration_config.py` | ADAPT → `schemas.py` |
| Tracer | `config/secrets/` keyring handling | ADAPT → `vault.py` local-key path |
| Tracer | `core/llm/providers/provider_credentials.py` | ADAPT → provider credentials resolve through the vault too |
| Tracer | `integrations/<vendor>/client.py` patterns | ADAPT → `integrations/_base/client.py` |

## Risks

| Risk | Mitigation |
|---|---|
| Proxy latency on hot paths | Local or in-cluster hop with a measured budget; a benchmark test asserts p50 overhead stays under the budget |
| A vendor SDK that resists adaptation blocks an integration | FR-018 makes replacement with a direct client the fallback; the base client already provides what most SDKs add |
| Proxy availability becomes the platform's availability | Co-located deployment (feature 030) and health-gated startup; failure is explicit and actionable rather than silent |
| Operators want a bypass for debugging | The verification command (FR-021) gives them what they actually need — confirmation a credential works — without exposing the value |
| Key management misconfiguration | Startup health check verifies stored credentials are decryptable, so a wrong key fails at boot rather than at 03:00 |

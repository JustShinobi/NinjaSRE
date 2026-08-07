# Splunk

SPL search against Splunk, counted before it is read, for the estates whose logs have been in Splunk longer than the services producing them.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Splunk authentication token, from a user with search access | yes | yes |
| `app` | Splunk app context searches run in | no | no |

```bash
ninjasre integrations setup splunk
ninjasre integrations verify splunk
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Splunk is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `splunk.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Settings → Tokens, or Splunk Cloud → Authentication tokens

| Permission | What it grants | Without it |
|---|---|---|
| `search` | run SPL searches in the app context | `splunk_log_statistics`, `splunk_sample_logs` |
| `rest_properties_get` | read server info, which the probe uses | `splunk_log_statistics` |

Splunk has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Every search costs indexer time**, and a badly bounded one costs it for everybody. The `index=` term is what bounds it, and a search without one scans every index the token can see.
- **`output_mode=json` is not the default.** Without it the answer is XML, which this client does not parse for Splunk.
- **Search head clustering means results can arrive out of order** across pages, so a sample is the newest of what came back rather than strictly the newest.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

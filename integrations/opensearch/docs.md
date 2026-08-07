# OpenSearch

Search over OpenSearch indices, counted by field before any document is read, for the deployments whose logs live in the fork rather than in Elasticsearch.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | OpenSearch user with read access to the log indices | yes | yes |
| `password` | That user's password, or the one the internal user database holds | yes | yes |
| `index` | Default index or data stream pattern to search | no | no |

```bash
ninjasre integrations setup opensearch
ninjasre integrations verify opensearch
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

OpenSearch is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `opensearch.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

OpenSearch Dashboards → Security → Internal users, or your identity provider

| Permission | What it grants | Without it |
|---|---|---|
| `indices:data/read/search` | search the indices this user can see | `opensearch_log_statistics`, `opensearch_sample_logs` |
| `cluster:monitor/health` | read cluster health, which the connectivity probe uses | `opensearch_log_statistics` |

OpenSearch has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Basic auth, not an API key.** OpenSearch's security plugin is where the roles live, and a user with the wrong role gets a 403 naming the index.
- **Deep paging is refused past `index.max_result_window`**, 10,000 by default.
- **AWS-managed OpenSearch signs with SigV4 instead**, which is a different integration shape; this one is for the self-managed and Docker deployments.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

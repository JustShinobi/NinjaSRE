# Elasticsearch

Search over Elasticsearch indices, counted by field before any document is read, for the deployments whose logs live there rather than in a hosted log product.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | Elasticsearch API key, base64 of id:api_key as Elasticsearch issues it | yes | yes |
| `index` | Default index or data stream pattern to search | no | no |

```bash
ninjasre integrations setup elasticsearch
ninjasre integrations verify elasticsearch
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Elasticsearch is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `elasticsearch.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Kibana → Stack Management → API keys, or POST /_security/api_key

| Permission | What it grants | Without it |
|---|---|---|
| `read` | search the indices this key is scoped to | `elasticsearch_log_statistics`, `elasticsearch_sample_logs` |
| `monitor` | read cluster health, which is what the connectivity probe uses | `elasticsearch_log_statistics` |

Elasticsearch has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **An API key carries index privileges, not cluster-wide ones.** A key that can search one data stream and not another produces a 403 naming the index, which is the useful part of the message.
- **Deep paging is refused past `index.max_result_window`**, 10,000 by default. Narrow the query rather than paging into it.
- **Field names differ by ingest pipeline.** ECS calls it `log.level`; a homegrown pipeline may call it `severity`, and the grouping field has to match whichever this cluster uses.
- **Statistics are computed here rather than by an aggregation**, over the capped page the search returned, and the result says so.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

# Coralogix

Coralogix log search over DataPrime or Lucene, counted by severity or application before any line is read.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Coralogix API key with DataQuerying permission | yes | yes |

```bash
ninjasre integrations setup coralogix
ninjasre integrations verify coralogix
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `eu1`, `eu2`, `us1`, `us2`, `ap1`, `ap2`.

## Permissions

Data Flow → API Keys, on the team whose data you investigate

| Permission | What it grants | Without it |
|---|---|---|
| `DataQuerying` | run DataPrime and Lucene queries | `coralogix_log_statistics`, `coralogix_sample_logs` |
| `LogsQuerying` | read the log entries a query matched | `coralogix_sample_logs` |

Coralogix has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The regional host is not derivable from the account name.** Coralogix has six and they share no pattern, so the region is configuration rather than a guess.
- **Queries are billed by scanned volume**, which is why the statistics capability caps what it reads and says so rather than scanning a window whole.
- **Archive queries reach further back and are much slower.** A query past hot retention answers from the archive or not at all, depending on the tier.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

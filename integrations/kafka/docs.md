# Kafka

Kafka through its REST Proxy: which topics and consumer groups exist on a cluster, and which groups are not in a stable state.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Kafka REST Proxy API key, or the cluster API key on Confluent Cloud | yes | yes |
| `password` | That key's secret | yes | yes |
| `cluster` | Kafka cluster id | no | yes |

```bash
ninjasre integrations setup kafka
ninjasre integrations verify kafka
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Kafka is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `kafka-rest.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Confluent Cloud → API keys, or the credentials your REST Proxy deployment uses

| Permission | What it grants | Without it |
|---|---|---|
| `DescribeTopics` | list topics on the cluster | `kafka_pipeline_health` |
| `DescribeGroups` | list consumer groups and their state | `kafka_recent_failures` |

Kafka has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Kafka's own protocol is binary and cannot route through an HTTP credential proxy.** This integration reads the REST Proxy — Confluent's, Strimzi's, or the Confluent Cloud API — and a cluster without one is not reachable.
- **Consumer lag is not in the group listing.** It is a per-group call against the lag endpoint, which Confluent Cloud has and the open-source proxy does not.
- **The cluster id is part of the path** and is substituted by the proxy from the stored configuration.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

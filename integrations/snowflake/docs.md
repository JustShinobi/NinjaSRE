# Snowflake

Snowflake over its SQL REST API: what is running in the account now, and the slowest statements the query history recorded.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Snowflake key-pair JWT or OAuth access token | yes | yes |
| `account` | Snowflake account identifier | no | yes |
| `warehouse` | Warehouse the statements run on | no | no |

```bash
ninjasre integrations setup snowflake
ninjasre integrations verify snowflake
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `account`.

Snowflake is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `acme-prod.snowflakecomputing.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Snowflake → Admin → Users, with a key pair registered, exchanged for a JWT

| Permission | What it grants | Without it |
|---|---|---|
| `MONITOR on the account` | read query history | `snowflake_session_statistics`, `snowflake_slow_queries` |
| `USAGE on the warehouse` | run the statements that read it | `snowflake_session_statistics`, `snowflake_slow_queries` |

Snowflake has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The account host is unique per Snowflake account.** There is no shared host to declare, so the region map is the account's own hostname and a deployment declares it.
- **Every statement costs warehouse time.** The queries here are against `information_schema` and are cheap, but they are not free and they wake a suspended warehouse.
- **Results arrive as rows and columns, not objects.** The client zips the two back together using the column names Snowflake returns in `resultSetMetaData`, so a grouping field is the column's own name in upper case.
- **Statements are asynchronous above a size threshold**, answering with a handle instead of data. This client uses a short timeout and reads the synchronous form.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

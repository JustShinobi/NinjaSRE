# Trello

What a Trello board is holding: the cards on it, which list each is in, and which were touched most recently.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Trello API token for the member whose boards are read | yes | yes |
| `board` | Trello board id | no | yes |

```bash
ninjasre integrations setup trello
ninjasre integrations verify trello
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

trello.com/app-key → Token, after generating an API key

| Permission | What it grants | Without it |
|---|---|---|
| `read` | read boards, lists, and cards | `trello_issue_statistics`, `trello_recent_issues` |
| `boards:read` | read the configured board, which the probe uses | `trello_issue_statistics` |

Trello has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Trello's key and token are both query parameters.** The proxy injects the token; the key is public and travels with it, which is Trello's own design and not something this integration chose.
- **Query strings reach access logs.** This is the vendor that makes that trade unavoidable, and it is the reason a header injection is preferred everywhere it is possible.
- **Lists are ids, not names.** Grouping by `idList` needs a second call to make the groups readable, which is a deliberate omission rather than an oversight.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

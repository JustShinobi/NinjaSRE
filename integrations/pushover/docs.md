# Pushover

Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Pushover application API token | yes | yes |
| `user_key` | Pushover user or group key | yes | yes |

```bash
ninjasre integrations setup pushover
ninjasre integrations verify pushover
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

pushover.net → Your Applications → API Token

| Permission | What it grants | Without it |
|---|---|---|
| `validate` | confirm the token and user key are valid | `pushover_recent_messages` |
| `messages:write` | push a message to the user or group | `pushover_post_message` |

Pushover has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Pushover has no history.** Nothing sent can be read back, which is why the read capability here reads the application's own licence record rather than messages.
- **The application token and the user key are both required** and mean different things: one identifies the sender, the other the recipient.
- **Emergency-priority messages retry until acknowledged.** This integration never sends at that priority, deliberately — an unacknowledged emergency is a page, and paging belongs to the incident vendors.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

# Slack

The conversation an incident is already happening in: what responders have said, and a finding delivered where they will read it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Slack bot token, which begins xoxb- | yes | yes |

```bash
ninjasre integrations setup slack
ninjasre integrations verify slack
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

api.slack.com/apps → your app → OAuth & Permissions → Bot User OAuth Token

| Permission | What it grants | Without it |
|---|---|---|
| `channels:history` | read messages in the channels the bot is in | `slack_recent_messages` |
| `chat:write` | post a message as the bot | `slack_post_message` |

Slack has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Slack answers 200 with `ok: false` for an application error.** A missing scope is a 200 whose body says `missing_scope`, and treating the status as the answer hides it.
- **The bot has to be in the channel.** `not_in_channel` is the most common failure and is a configuration problem rather than a permission one.
- **Timestamps are the message id.** `ts` is a string like `1754503600.000100` and loses precision if it is read as a float.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

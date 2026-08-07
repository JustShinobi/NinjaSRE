# Discord

A Discord channel used for incident response: what has been said recently, and a finding posted into it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Discord bot token | yes | yes |
| `channel_id` | Default channel id | no | yes |

```bash
ninjasre integrations setup discord
ninjasre integrations verify discord
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

discord.com/developers → your application → Bot → Reset Token

| Permission | What it grants | Without it |
|---|---|---|
| `View Channel` | read the channel's message history | `discord_recent_messages` |
| `Send Messages` | post a message into the channel | `discord_post_message` |

Discord has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The channel id is part of the path** and is substituted by the proxy, so a capability cannot post into another channel.
- **Message history needs the Read Message History permission** separately from View Channel, and the failure is a 403 that names neither.
- **Discord's rate limits are per route and returned in headers.** The client honours `Retry-After` up to a ceiling rather than sleeping through an investigation.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

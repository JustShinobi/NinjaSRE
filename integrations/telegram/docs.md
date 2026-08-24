# Telegram

A Telegram chat used as an alerting channel: what has arrived recently, and a finding delivered into it.

## Setup

Secret and required status are declared once, in this package's `schema.py`;
this table does not repeat them. It carries what `schema.py` does not show in a
browsable form: what each field is, the minimum permission it needs when it is
secret, and a guide to producing it.

| Field | What it is | Minimum permission | Guide |
|---|---|---|---|
| `token` | Telegram bot token, as BotFather issued it | this token does not carry scope — treat it as full access | [Telegram Bot API](https://core.telegram.org/bots) |

Source: Telegram's own Bot API documentation. A bot token has no scope system
— it can do everything the Bot API allows that bot to do.

```bash
ninjasre integrations setup telegram
ninjasre integrations verify telegram
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Telegram → @BotFather → /mybots → API Token

| Permission | What it grants | Without it |
|---|---|---|
| `getUpdates` | read updates addressed to the bot | `telegram_recent_messages` |
| `sendMessage` | send a message to a chat the bot is in | `telegram_post_message` |

Telegram has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The token is in the URL path.** That is Telegram's design and it is the reason the proxy substitutes it there rather than in a header — a bot token in a path is still a credential and must not be in the client.
- **`getUpdates` is a queue, not a history.** Reading consumes updates, and a chat using a webhook has none to read at all.
- **A bot cannot read group messages by default.** Privacy mode has to be turned off in BotFather, and until it is the history is nearly empty.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

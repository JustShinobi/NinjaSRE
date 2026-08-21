# Twilio

Twilio as an SMS notification path: the messages this account has sent recently, and a finding delivered to a responder's phone.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Twilio account SID, which doubles as the basic-auth username | yes | yes |
| `password` | Twilio auth token, or an API key secret | yes | yes |
| `account_sid` | Twilio account SID used in the path | no | yes |

```bash
ninjasre integrations setup twilio
ninjasre integrations verify twilio
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

console.twilio.com → Account → API keys & tokens

| Permission | What it grants | Without it |
|---|---|---|
| `messages:read` | read the account's message history | `twilio_recent_messages` |
| `messages:create` | send a message from the account | `twilio_post_message` |

Twilio has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The account SID is both the username and a path segment**, and the proxy supplies both. A capability cannot be pointed at another account.
- **A message is queued, not delivered.** `status` moves through `queued`, `sent`, `delivered`, or `failed` asynchronously, so a successful call is not a delivered message.
- **SMS costs money per message** and per segment; a long finding is several segments and is billed as such.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

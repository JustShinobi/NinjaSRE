# Rocket.Chat

A Rocket.Chat channel used for incident response: what has been said, and a finding posted into it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Rocket.Chat personal access token | yes | yes |
| `user_id` | The user id the token belongs to | yes | yes |

```bash
ninjasre integrations setup rocket_chat
ninjasre integrations verify rocket_chat
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Rocket.Chat is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `rocketchat.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Rocket.Chat → My Account → Personal Access Tokens

| Permission | What it grants | Without it |
|---|---|---|
| `view-c-room` | read a public channel's history | `rocket_chat_recent_messages` |
| `post-message` | post a message into a channel | `rocket_chat_post_message` |

Rocket.Chat has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Both headers are required.** `X-Auth-Token` alone is a 401 that does not say the user id is missing.
- **Rocket.Chat is self-hosted**, so the host is configuration and the API version differs more between deployments than a SaaS vendor's would.
- **Channel history needs the channel name, not its id**, on the `channels.*` endpoints, and the id is what most other surfaces hand you.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

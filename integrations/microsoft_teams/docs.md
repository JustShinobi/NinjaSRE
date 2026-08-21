# Microsoft Teams

The Teams channel an incident is being run from: what has been said, and a finding posted where the responders are.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Microsoft Graph access token for an application with channel permissions | yes | yes |
| `team_id` | Teams group id the channel belongs to | no | yes |

```bash
ninjasre integrations setup microsoft_teams
ninjasre integrations verify microsoft_teams
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Entra ID → App registrations → your application → Certificates & secrets, exchanged for a token against https://graph.microsoft.com

| Permission | What it grants | Without it |
|---|---|---|
| `ChannelMessage.Read.All` | read channel messages | `microsoft_teams_recent_messages` |
| `ChannelMessage.Send` | post a message to a channel | `microsoft_teams_post_message` |

Microsoft Teams has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Application permissions for channel messages require admin consent** and, for reads, a Microsoft 365 licence with the protected API request approved. Without it the call is a 403 that names neither.
- **Message bodies are HTML by default**, so a plain-text finding arrives with its line breaks lost unless the content type says otherwise.
- **Access tokens expire in an hour**, so the stored credential is refreshed rather than being long-lived.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

# WhatsApp

A WhatsApp Business number used for on-call notification: the message templates available, and a finding delivered to a responder.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Meta system user access token with whatsapp_business_messaging | yes | yes |
| `phone_number_id` | WhatsApp Business phone number id | no | yes |

```bash
ninjasre integrations setup whatsapp
ninjasre integrations verify whatsapp
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

developers.facebook.com → your app → WhatsApp → API Setup → access token

| Permission | What it grants | Without it |
|---|---|---|
| `whatsapp_business_management` | read the number's message templates | `whatsapp_recent_messages` |
| `whatsapp_business_messaging` | send a message from the number | `whatsapp_post_message` |

WhatsApp has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **A free-form message can only be sent inside a 24-hour customer service window.** Outside it, only an approved template may be sent, and the failure is a 400 naming a policy rather than a permission.
- **Templates need approval and can be rejected.** The first capability exists to make that visible before an incident rather than during one.
- **There is no message history to read.** WhatsApp delivers inbound messages by webhook; nothing can be fetched afterwards, which is why the read capability here reads templates.
- **A posted message cannot be unsaid.** It can be followed by a correction, which is what the rollback plan on the write capability describes, and that is not the same thing as undoing it.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

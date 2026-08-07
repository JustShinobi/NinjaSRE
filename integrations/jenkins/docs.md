# Jenkins

Jenkins build history: how a job has been doing lately, and the builds that failed, for the estates whose pipelines still run there.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Jenkins user id | yes | yes |
| `password` | That user's API token, not their password | yes | yes |

```bash
ninjasre integrations setup jenkins
ninjasre integrations verify jenkins
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Jenkins is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `jenkins.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your Jenkins user → Configure → API Token → Add new Token

| Permission | What it grants | Without it |
|---|---|---|
| `Overall/Read` | read the Jenkins instance at all | `jenkins_pipeline_statistics`, `jenkins_failed_runs` |
| `Job/Read` | read job configuration and build history | `jenkins_pipeline_statistics`, `jenkins_failed_runs` |

Jenkins has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The `tree` parameter is the whole API.** Without it Jenkins returns everything it knows about every job, which on a real installation is megabytes.
- **Build history is bounded by the job's own discard policy**, so 'no failures in the window' can mean the records were discarded.
- **A basic-auth password is not an API token**, and Jenkins accepts both while some security realms reject the first. The token is what to store.
- **CSRF protection applies to writes**, not to the reads here, which is why this integration reads only.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.

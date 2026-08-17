# Quickstart

From nothing to a finished investigation. Everything you need is on this page —
you should not have to open anything else, and if you do, that is a defect in
this page rather than in you.

Budget about fifteen minutes, most of it waiting for containers to pull.

## What you need first

- **Docker** with the Compose plugin. `docker compose version` should print
  something.
- **One model provider API key**, or a local model. Anthropic, OpenAI, Azure
  OpenAI, AWS Bedrock, Google Gemini, Google Vertex AI, OpenRouter, NVIDIA NIM,
  and Ollama all work the same way from here on.
- **About 4 GB of free memory.**

You do not need Kubernetes, a cloud account, or a NinjaSRE account. There is no
NinjaSRE account; nothing here talks to us.

## 1. Get the deployment files

```sh
git clone https://github.com/ninjasre/ninjasre.git
cd ninjasre/deploy/compose
cp .env.example .env
```

`.env.example` documents every setting, its default, and what it affects. You
are about to change two lines in it.

## 2. Set the two things that have no default

Generate an encryption key. This is what protects every integration credential
the deployment stores:

```sh
openssl rand -base64 32
```

Open `.env` and set two values:

```ini
NINJASRE_DATABASE_ENCRYPTION_KEY=<the key you just generated>
ANTHROPIC_API_KEY=<your provider key>
```

Use whichever provider variable matches your key — `OPENAI_API_KEY`,
`GOOGLE_API_KEY`, and the rest are all in the file with a comment saying what
each one is for.

> **Keep that encryption key.** Losing it means every stored credential has to
> be entered again. It is not recoverable, deliberately: a key the platform
> could recover is a key an attacker with the database can recover.

## 3. Start it

```sh
docker compose up -d
```

Four containers start: the application, the web console, PostgreSQL, and the
credential proxy. Database migrations apply on first start.

Watch for the admin token, which is generated once and printed once:

```sh
docker compose logs app | grep -i "admin token"
```

Copy it somewhere. It will not be printed again.

## 4. Check it can actually investigate

```sh
docker compose exec app ninjasre doctor
```

Every check reports what is wrong *and what to do about it*. A diagnostic that
says "provider not configured" and stops has moved the work rather than done it.

Read the verdict line at the top. If it says this deployment can investigate,
carry on. If it does not, the failing check names the remedy — do that and run
`doctor` again.

## 5. Run your first investigation

```sh
docker compose exec app ninjasre investigate "checkout latency doubled at 14:02"
```

You will see the investigation proceed: the stages it runs, the capabilities it
calls, and the evidence each one returned. At the end it prints a root cause
with the observations that support it. Every claim names what it was drawn from
— a conclusion without evidence behind it is a hypothesis here, never a finding.

With no integrations configured, it will reason from what you told it and say
plainly what it could not check. That is the correct behaviour and it is worth
seeing once: the platform does not invent an observation it did not make.

## 6. Give it something to look at

An investigation is only as good as what it can see. Add one integration:

```sh
docker compose exec -it app ninjasre integrations setup grafana
```

It prompts for whatever that vendor's credential needs and writes the values to
the vault. There is deliberately no way to pass a credential as a command-line
argument — one typed as an argument is in your shell history before the process
starts.

Then check it works:

```sh
docker compose exec app ninjasre integrations health
```

One line: how many integrations are healthy, how many are not answering, and how
many are not configured yet.

Now run the investigation again. It has somewhere to look.

## 7. Open the console

```
http://localhost:8421
```

Sign in with the admin token from step 3. The console shows runs as they happen,
the queue of things waiting on a person, what the platform has remembered, and
what a period has cost.

## What you have

A deployment that investigates incidents, records the evidence behind every
conclusion, and remembers what it learned. Nothing has left your machine except
the calls to the model provider you configured.

## Where to go next

- **[Deployment](../deployment/index.md)** — the three profiles, upgrading,
  backups, key rotation, and running with no internet at all.
- **[Configuration](../configuration/index.md)** — every setting, generated from
  the same catalogue `.env.example` comes from.
- **[Capabilities](../capabilities/index.md)** — everything the agent can call,
  and the side-effect level each one is gated at.
- **[Integrations](../integrations/index.md)** — every vendor, what credential
  it needs, and which permissions verification actually probes.
- **[Security](../security/index.md)** — where the trust boundary is and what
  each control is defending against.

## If something went wrong

```sh
docker compose exec app ninjasre doctor --bundle /tmp/bundle.md
```

That writes a redacted report — configuration with secrets removed, recent logs,
health output, and version information. **Read it before you share it.** Nothing
is transmitted: there is no telemetry here, so nothing sends a crash report on
your behalf, and what happens to that file is your decision.

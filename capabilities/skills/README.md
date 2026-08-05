# capabilities/skills/ — methodology, disclosed progressively

One directory per skill, each holding a `SKILL.md`. There is no index: the
presence of the file is the whole of the registration protocol, which is what
makes adding a skill a matter of creating one directory.

## What a manifest looks like

```
---
name: observability-datadog
description: Datadog log, metric, and APM investigation. Statistics before samples.
domain: observability
applies_when:
  alert_sources: [datadog]
  tags: [logs, metrics, apm]
directs_tools:
  - datadog_log_statistics
  - datadog_sample_logs
requires:
  integrations: [datadog]
---

The body. Markdown, methodology, loaded only when this skill is selected.
```

Frontmatter is read by a deliberately small parser: scalars, flat lists in
either notation, and one level of nesting. Anything else is rejected by name
rather than interpreted, because a manifest that parses into something other
than what its author wrote is worse than one that fails.

## The two rules the build enforces

**Everything in `directs_tools` must resolve to a registered tool.** A dangling
reference is discovered during an investigation otherwise, which is the worst
available moment.

**A body directs tools; it never instructs shell execution.** A skill telling
the model to run a command has routed around the approval gate, the rollback
plan, and the audit record that the tool layer exists to provide. The lint
fires on instructions to execute — `run \`kubectl delete\``, a `bash` fenced
block, a `$` prompt — and not on prose about a command, so a skill may still
say what the tool it directs is equivalent to.

## Budgets

The frontmatter and description are paid for on every turn, for every skill the
team has; the body is paid for only by the turn that selects it. Both ceilings
are named constants in `config/constants/capabilities.py`, and both are
enforced by a test rather than estimated.

`_templates/` holds starting points for the domains an integration usually
needs. Templates are deliberately incomplete and are skipped by discovery.

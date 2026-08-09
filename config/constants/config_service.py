"""The configuration service: its bounds, its stored keys, and its budgets.

Configuration is the one subsystem whose input is written by an operator rather
than produced by the platform, so every bound here exists because something on
the other side of it is unbounded. A hierarchy nobody limited is a merge that
recurses until the stack ends; a cache keyed on team is a cache that grows with
the number of teams; a settings document nobody limited is a JSONB column
holding a log file somebody pasted.

The two *keys* are the exception and are worth reading twice. A node's stored
document is an envelope with two members — the settings, and the field policies
declared at that node. They are separate because the merge must not interpret
anything (FR-003): a policy stored inside the settings would be a control key,
and a control key is the first line of a configuration language.
"""

from __future__ import annotations

from typing import Final

# --- The stored envelope -----------------------------------------------------

#: Where a node's own configuration values live inside its stored document.
#: Everything under this key is data and nothing under it is ever interpreted.
SETTINGS_KEY: Final = "settings"

#: Where the field policies declared at a node live. Outside the settings, so
#: the merge never sees them and no configuration value can pass for one.
FIELD_POLICIES_KEY: Final = "field_policies"

#: What separates the segments of a configuration path. Paths are dotted
#: strings — ``policies.masking.level`` — because they are read in an error
#: message, an audit row, and a provenance table, and all three are text.
PATH_SEPARATOR: Final = "."

# --- Bounds ------------------------------------------------------------------

#: How deep the hierarchy may go, root inclusive. Org, division, team, squad is
#: four; the headroom above that is for deployments that group by region or
#: business unit as well. A tree deeper than this is a modelling error, and
#: every resolution beneath it would pay for it.
MAX_HIERARCHY_DEPTH: Final[int] = 12

#: How deep one configuration document may nest. The merge recurses per level,
#: and an operator-supplied document is the one input that could be shaped to
#: exhaust the stack.
MAX_CONFIG_DEPTH: Final[int] = 16

#: How many leaf values one node's settings may hold. Large enough for a fully
#: specified organisation, small enough that a paste accident is refused rather
#: than stored.
MAX_CONFIG_LEAVES: Final[int] = 2_000

#: How long one configuration string may be. Prompts are the long ones, and a
#: system prompt beyond this is a document that belongs in the knowledge base.
MAX_CONFIG_STRING_CHARS: Final[int] = 20_000

#: How many entries one node may put in a list-valued field.
MAX_CONFIG_LIST_ITEMS: Final[int] = 200

#: How many field policies one node may declare.
MAX_FIELD_POLICIES: Final[int] = 200

#: How many effective configurations one resolver keeps. One per node in the
#: tenant's tree is the working set; beyond that, least-recently-used is
#: evicted. Unbounded would grow with the number of teams and never shrink.
MAX_EFFECTIVE_CONFIG_CACHE_ENTRIES: Final[int] = 256

#: How many validation errors are reported at once. An operator fixing a
#: document one error per submission stops using the document.
MAX_REPORTED_FIELD_ERRORS: Final[int] = 50

# --- Budgets -----------------------------------------------------------------

#: What a cold effective-config resolution on a four-level hierarchy carrying a
#: large configuration must stay within (SC-003). It sits on the investigation
#: path once per run, so the budget is stated in milliseconds and asserted by a
#: benchmark rather than left to be noticed.
EFFECTIVE_CONFIG_COLD_BUDGET_MS: Final[float] = 50.0

#: What a cached resolution must stay within. Two orders of magnitude below the
#: cold path, because if it is not, the cache is not earning its invalidation
#: risk.
EFFECTIVE_CONFIG_CACHED_BUDGET_MS: Final[float] = 1.0

# --- Model roles -------------------------------------------------------------

#: The roles a deployment may bind a provider and model to. A closed set: a
#: typo in a role name would otherwise be configuration nobody ever reads,
#: silently leaving that role on the default while the console showed it bound.
MODEL_ROLE_INVESTIGATOR: Final = "investigator"
MODEL_ROLE_SUBAGENT: Final = "subagent"
MODEL_ROLE_INTAKE: Final = "intake"
MODEL_ROLE_DIAGNOSE: Final = "diagnose"
MODEL_ROLE_EXTRACTION: Final = "extraction"
MODEL_ROLE_EMBEDDING: Final = "embedding"
#: Choosing which capability to run next, and writing a summary. Both are jobs a
#: small local model does well and neither had a role of its own, so a deployment
#: that wanted the cheap model for them and something else for the final
#: synthesis had no way to say so.
MODEL_ROLE_SELECTION: Final = "selection"
MODEL_ROLE_SUMMARISATION: Final = "summarisation"

MODEL_ROLES: Final[tuple[str, ...]] = (
    MODEL_ROLE_INVESTIGATOR,
    MODEL_ROLE_SUBAGENT,
    MODEL_ROLE_INTAKE,
    MODEL_ROLE_DIAGNOSE,
    MODEL_ROLE_EXTRACTION,
    MODEL_ROLE_EMBEDDING,
    MODEL_ROLE_SELECTION,
    MODEL_ROLE_SUMMARISATION,
)

#: The agent roles a deployment may override the system prompt for. Same
#: closure, same reason.
PROMPT_ROLE_INVESTIGATOR: Final = "investigator"
PROMPT_ROLE_INTAKE: Final = "intake"
PROMPT_ROLE_DIAGNOSE: Final = "diagnose"

PROMPT_ROLES: Final[tuple[str, ...]] = (
    PROMPT_ROLE_INVESTIGATOR,
    PROMPT_ROLE_INTAKE,
    PROMPT_ROLE_DIAGNOSE,
)

# --- Audit -------------------------------------------------------------------

#: The resource kind configuration audit events are recorded against.
CONFIG_AUDIT_RESOURCE_KIND: Final = "config_node"

#: The actions a configuration change is audited under.
CONFIG_AUDIT_ACTION_SET: Final = "config.field.set"
CONFIG_AUDIT_ACTION_CLEAR: Final = "config.field.clear"
CONFIG_AUDIT_ACTION_POLICY: Final = "config.policy.set"
CONFIG_AUDIT_ACTION_TEMPLATE: Final = "config.template.apply"

#: How much of a changed value one audit row records. A prompt override is
#: thousands of characters and the audit table is not where a diff belongs;
#: beyond this the value is truncated and the row says so.
MAX_AUDITED_VALUE_CHARS: Final[int] = 1_000

# --- Templates ---------------------------------------------------------------

#: The directory the shipped templates live in, relative to the template engine.
GOLDEN_TEMPLATE_DIRECTORY: Final = "golden"

#: The extension a template document carries.
TEMPLATE_FILE_SUFFIX: Final = ".yml"

#: The templates NinjaSRE ships. Named here rather than discovered, because a
#: template that stopped loading would otherwise be a template that silently
#: stopped being offered — and the console renders this list.
GOLDEN_TEMPLATES: Final[tuple[str, ...]] = (
    "incident-triage-slack",
    "ci-failure-investigation",
    "cost-investigation",
    "postmortem-authoring",
    "alert-fatigue-reduction",
    "dr-validation",
    "observability-advisory",
)

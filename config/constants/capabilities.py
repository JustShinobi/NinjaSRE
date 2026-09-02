"""Every bound the capability catalogue runs inside (Constitution Article II).

Two of these decide whether the system works at all at catalogue scale.

``MAX_SKILL_METADATA_TOKENS`` is the per-skill entry fee. It is paid once per
turn for every skill in the resolved catalogue, whether or not the skill is
used, because the model has to see the index to choose from it. Multiply it by
the number of integrations and the product is the standing context cost of
owning a large catalogue.

``MAX_CATALOGUE_METADATA_TOKENS`` is that product's ceiling, measured rather
than estimated. It is what stops the catalogue growing into the context budget
one integration at a time, with nothing failing until an investigation runs out
of room mid-turn.

The tool ceiling is deliberately *not* part of that product. A tool's
description is paid for only when the tool is selected, and the number selected
is capped per turn — so tool prose is bounded by the schema cap rather than by
the size of the catalogue. It gets its own per-tool ceiling instead, because
one tool carrying an essay still wastes a slot on every turn it wins one.

The scoring weights are here for the same reason a loop ceiling is: a weight
written at the call site is a tuning decision nobody can find again, and the
ablation suite has to be able to neutralise each signal independently.
"""

from __future__ import annotations

from typing import Final

# --- Progressive disclosure --------------------------------------------------

#: Cost of one skill's catalogue entry — frontmatter plus description. The body
#: is not counted because it is not loaded until the skill is selected, which is
#: the whole point of the split.
MAX_SKILL_METADATA_TOKENS: Final[int] = 128

#: Cost of the whole skill index together — what a turn pays before it has
#: chosen anything. Sized so that a catalogue of roughly eighty-five
#: integrations, each shipping one methodology skill, plus the cross-vendor
#: skills, still leaves the large majority of the window for the investigation.
MAX_CATALOGUE_METADATA_TOKENS: Final[int] = 14_000

#: A selected skill's body, loaded into the turn that selected it. A skill that
#: cannot say what it means inside this is a skill that should be two skills.
MAX_SKILL_BODY_TOKENS: Final[int] = 4_000

#: A tool's description as the model reads it. Longer than this and the schema
#: payload is carrying prose that belongs in the skill body.
MAX_TOOL_DESCRIPTION_TOKENS: Final[int] = 192

#: How much of a failed capability's own error text reaches the model and the
#: console, in characters.
#:
#: The message used to carry the exception's class name and nothing else, so a
#: reader looking at an incident card saw the word "ValueError". Carrying the
#: text instead means carrying whatever a vendor put in it, and a gateway
#: having a bad day answers with a page of HTML — which would arrive in the
#: turn's context at the moment the investigation can least afford it. The
#: whole of it is still kept in the result's ``detail``, which the trace holds
#: and nothing sends to a model.
MAX_CAPABILITY_ERROR_MESSAGE_CHARS: Final[int] = 300

# --- Discovery ---------------------------------------------------------------

#: The manifest that makes a directory a skill. Its presence is the whole of the
#: registration protocol — there is no list of skills to add a line to.
SKILL_MANIFEST_FILENAME: Final = "SKILL.md"

#: The attribute a declared tool carries. Discovery scans module attributes for
#: it rather than importing a registry, so adding a tool edits no existing file.
CAPABILITY_MARKER_ATTRIBUTE: Final = "__ninjasre_capability__"

#: Where discovery walks. The first two are the cross-vendor catalogue; the
#: third is the per-vendor subpackage every integration exposes its tools from.
CAPABILITY_TOOLS_PACKAGE: Final = "capabilities.tools"
CAPABILITY_SKILLS_PACKAGE: Final = "capabilities.skills"
INTEGRATION_TOOLS_SUBPACKAGE: Final = "tools"

#: How long a discovery walk over the real packages is reused before it is
#: walked again. The walk imports sixteen thousand modules through ``pkgutil``
#: and parses every skill manifest; a request that needs the catalogue paid
#: for the whole of it — the capability catalogue, the integration catalogue,
#: the checklist and the integrations screen each once, on every render.
#: Thirty seconds keeps "adding a capability edits no existing file" true at
#: runtime to within one console refresh, which is what it was ever true to.
INSTALLED_CATALOGUE_CACHE_TTL_SECONDS: Final[float] = 30.0

#: Skipped by the skill walk. Templates are text for a scaffold to copy; they
#: are deliberately incomplete and must never enter the catalogue.
SKILL_TEMPLATE_DIRECTORY: Final = "_templates"

# --- Selection ---------------------------------------------------------------

#: Skill bodies loaded into one turn. Each is methodology the model has to hold
#: alongside the incident, and a turn reading four competing methodologies is a
#: turn that follows none of them.
MAX_SELECTED_SKILLS: Final[int] = 3

#: Evidence sources that make a capability *secondary*: cheap, vendor-free, and
#: useful on any incident. These are what the reserved slots hold, because a
#: flood of high-scoring vendor tools would otherwise crowd out the reasoning
#: and recall capabilities precisely when an investigation is going badly.
SECONDARY_EVIDENCE_SOURCES: Final[frozenset[str]] = frozenset(
    {"reasoning", "memory", "knowledge_base", "runbook"}
)

# --- Scoring weights ---------------------------------------------------------

#: The vendor that holds the thing the incident is about. Alert resolution has
#: already matched the alert onto an estate resource by the time capabilities
#: are ranked, and that resource says which system holds it — so this is known
#: before the first model call, like everything else in the formula.
#:
#: It is the strongest signal that does not come from the planner, and it
#: outweighs the alert source deliberately. A backup job failing on a Proxmox
#: node is a question about Proxmox; the notification about it happens to have
#: arrived through Alertmanager, and that is a fact about delivery rather than
#: about what broke.
SCORE_SUBJECT_SOURCE_MATCH: Final[float] = 40.0

#: The alert names its own source, and a capability that reads that source can
#: say more about the notification — when it started, how often it has fired,
#: what else fired with it.
#:
#: Worth a term and not worth the largest one. This weight was 40, equal to a
#: subject match and larger than every other signal put together, and a
#: deployment whose alerts all arrive through one system therefore ranked that
#: system's tools first for every incident it ever had. An investigation that
#: spends its budget reading the alerting system about an alert it was handed
#: learns nothing it did not start with.
SCORE_ALERT_SOURCE_MATCH: Final[float] = 10.0

#: A capability whose declared domain matches the incident's.
SCORE_DOMAIN_MATCH: Final[float] = 15.0

#: Per overlapping tag, up to the cap. Tags are cheap to write and cheap to get
#: wrong, so no amount of tag overlap may outweigh a source match on its own.
SCORE_TAG_OVERLAP_PER_TAG: Final[float] = 8.0
SCORE_TAG_OVERLAP_MAX: Final[float] = 24.0

#: Lexical overlap between the incident text and the declared use cases, scaled
#: into this ceiling.
SCORE_USE_CASE_SIMILARITY_MAX: Final[float] = 20.0

#: Historical effectiveness, scaled into this ceiling from the unit interval the
#: provider returns. Neutral by default, so a deployment with no history yet
#: scores exactly as it would with the signal ablated.
SCORE_EFFECTIVENESS_MAX: Final[float] = 20.0

#: An anti-example that matches the incident. Negative and large enough to sink
#: a capability that every other signal likes, because an anti-example is the
#: author saying "not this one" about precisely this situation.
SCORE_ANTI_EXAMPLE_PENALTY: Final[float] = -60.0

#: Words too common to carry meaning in a lexical overlap. Without this, every
#: capability matches every alert on "the" and the signal is noise.
SCORE_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "when",
        "with",
    }
)

#: Shortest word that counts toward lexical overlap.
SCORE_MINIMUM_TERM_LENGTH: Final[int] = 3


__all__ = [
    "CAPABILITY_MARKER_ATTRIBUTE",
    "CAPABILITY_SKILLS_PACKAGE",
    "CAPABILITY_TOOLS_PACKAGE",
    "INSTALLED_CATALOGUE_CACHE_TTL_SECONDS",
    "INTEGRATION_TOOLS_SUBPACKAGE",
    "MAX_CAPABILITY_ERROR_MESSAGE_CHARS",
    "MAX_CATALOGUE_METADATA_TOKENS",
    "MAX_SELECTED_SKILLS",
    "MAX_SKILL_BODY_TOKENS",
    "MAX_SKILL_METADATA_TOKENS",
    "MAX_TOOL_DESCRIPTION_TOKENS",
    "SCORE_ALERT_SOURCE_MATCH",
    "SCORE_ANTI_EXAMPLE_PENALTY",
    "SCORE_DOMAIN_MATCH",
    "SCORE_EFFECTIVENESS_MAX",
    "SCORE_MINIMUM_TERM_LENGTH",
    "SCORE_SUBJECT_SOURCE_MATCH",
    "SCORE_STOP_WORDS",
    "SCORE_TAG_OVERLAP_MAX",
    "SCORE_TAG_OVERLAP_PER_TAG",
    "SCORE_USE_CASE_SIMILARITY_MAX",
    "SECONDARY_EVIDENCE_SOURCES",
    "SKILL_MANIFEST_FILENAME",
    "SKILL_TEMPLATE_DIRECTORY",
]

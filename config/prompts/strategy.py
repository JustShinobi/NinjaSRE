"""The synthesis prompt, its version, and how a playbook is shown to the agent.

The version lives in this file rather than with the bounds, and that placement is
the point. A playbook records the version it was generated under so that a
quality shift can be attributed to a prompt change rather than to the corpus
moving underneath it — and the only way that stays true is if the number a
reviewer has to bump is on the screen next to the text they just edited.

**Bump ``STRATEGY_PROMPT_VERSION`` in the same change that edits any string in
this file that the model reads.**

Two things about the prompt itself are worth defending.

The anti-patterns section is given its input explicitly — the unresolved and
low-effectiveness episodes, named as such — rather than being asked for as a
fourth bullet over the whole set. A model asked to "also list what did not work"
over a mixed set produces plausible-sounding cautions drawn from the runs that
succeeded, which is the one section where a fabrication is indistinguishable from
a finding. It is also the section with the most value in it: runbooks describe
what should work, and only accumulated failure describes what looked promising
and was not.

And the agent is shown the episode count and the date range beside every
playbook. A synthesis over three investigations from last week and one over
twenty across a year deserve different weight, and an agent shown neither number
has no way to apply any.
"""

from __future__ import annotations

from typing import Final

# --- The synthesis call -------------------------------------------------------

#: Bumped whenever any string below that the model reads is edited. Stored on
#: every playbook this prompt produces.
STRATEGY_PROMPT_VERSION: Final[int] = 1

#: The system prompt for the single synthesis call.
STRATEGY_SYNTHESIS_SYSTEM_PROMPT: Final[str] = (
    "You are turning a set of finished SRE investigations into one playbook for the "
    "next engineer who meets this failure. Every investigation you are given is of "
    "the same class of failure on the same component. Write only what the set "
    "actually supports.\n\n"
    "Produce four sections.\n\n"
    "1. Common root causes — the causes that recur across these investigations. A "
    "cause established once is not a pattern; say how many of the runs support each "
    "one. Do not include causes nobody established.\n\n"
    "2. Recommended investigation steps — an ordered sequence, most effective first. "
    "Order by what actually produced findings in these runs, not by what a runbook "
    "would recommend.\n\n"
    "3. Key capabilities — the specific capabilities and queries that produced the "
    "findings, named as the runs named them. A capability nobody called is not a "
    "recommendation.\n\n"
    "4. Anti-patterns — approaches that looked promising in these investigations and "
    "did not help. You are given the runs that failed to establish a cause "
    "separately; draw this section from those, and from those only. This is the most "
    "valuable section and the easiest to get wrong: an anti-pattern invented from a "
    "run that succeeded will send the next engineer away from the thing that "
    "worked.\n\n"
    "Be specific and be short. Each item is one sentence a tired engineer reads at "
    "three in the morning. If a section has nothing the evidence supports, return it "
    "empty rather than filling it."
)

#: The user message for that call.
STRATEGY_SYNTHESIS_REQUEST: Final[str] = (
    "Issue type: {issue_type}\n"
    "Component: {component_key}\n"
    "Investigations in this set: {count} ({resolved} established a root cause, "
    "{unresolved} did not)\n\n"
    "Investigations that established a root cause:\n{resolved_episodes}\n\n"
    "Investigations that did not establish a root cause — the anti-patterns section "
    "is drawn from these:\n{unresolved_episodes}\n\n"
    "Produce the playbook."
)

#: How one episode is presented to the synthesis call.
STRATEGY_SYNTHESIS_EPISODE: Final[str] = (
    "- [{episode_id}] {occurred}\n"
    "  what was wrong: {issue_description}\n"
    "  root cause: {root_cause}\n"
    "  capabilities called, in order: {capabilities}\n"
    "  effectiveness: {effectiveness}\n"
    "  summary: {summary}"
)

#: Stands in for either half of the set when it is empty. Named rather than left
#: blank, because "all of these runs failed" is a real and informative case — the
#: playbook is then entirely anti-patterns — and an empty heading reads to the
#: model as an omission rather than as a fact.
STRATEGY_NO_RESOLVED_EPISODES: Final[str] = (
    "None. No investigation in this set established a root cause, so there are no "
    "confirmed causes to report — the playbook is what did not work."
)
STRATEGY_NO_UNRESOLVED_EPISODES: Final[str] = (
    "None. Every investigation in this set established a root cause, so there are no "
    "dead ends to report. Leave the anti-patterns section empty."
)

# --- What the agent is shown --------------------------------------------------

#: The heading on a playbook in the shaped recall result. It says what the thing
#: is before it says anything it contains: an agent that reads a synthesised
#: generalisation as an observation of this incident will cite it as one.
STRATEGY_RECALL_HEADER: Final[str] = (
    "SYNTHESISED PLAYBOOK [{label}] — not an observation of this incident. This is a "
    "generalisation over {count} previous investigation(s) of {issue_type} on "
    "{component_key}, between {earliest} and {latest}. Weigh it against what you have "
    "actually observed; where it disagrees with your evidence, your evidence wins."
)

#: One section of a playbook, as the agent is shown it.
STRATEGY_RECALL_SECTION: Final[str] = "  {title}:\n{items}"

#: Human titles for the four sections, in presentation order.
STRATEGY_SECTION_TITLES: Final[dict[str, str]] = {
    "common_root_causes": "Common root causes",
    "recommended_investigation_steps": "Recommended investigation steps, most effective first",
    "key_capabilities": "Capabilities and queries that produced findings",
    "anti_patterns": "Anti-patterns — tried in previous runs, did not help",
}

#: Appended when an operator has amended the playbook. Marked, because a human
#: correction outranks the generated text above it and the agent has to be able
#: to tell which is which.
STRATEGY_RECALL_OPERATOR_EDITS: Final[str] = (
    "  Operator amendments — written by a human who reviewed this playbook, and "
    "authoritative over the generated sections above:\n{items}"
)

#: What the trace and the console record when synthesis was not attempted because
#: the corpus is too small. A reason rather than a silence: a deployment where no
#: playbook is ever generated should look like a young corpus, not like a broken
#: feature.
STRATEGY_BELOW_THRESHOLD: Final[str] = (
    "{found} investigation(s) of {issue_type} on {component_key} — below the {minimum} "
    "needed to synthesise a playbook. Individual episodes are unaffected."
)

#: Recorded when synthesis did not return a playbook. Synthesis never fails a
#: recall, so this is the whole consequence of it failing.
STRATEGY_SYNTHESIS_FAILED: Final[str] = (
    "Strategy synthesis did not return a playbook ({failure}). Individual episode "
    "recall is unaffected and nothing was written."
)

#: Recorded when the team's strategy switch is off.
STRATEGY_DISABLED: Final[str] = (
    "Synthesised playbooks are switched off for this team. Individual episodes are "
    "returned as usual."
)


__all__ = [
    "STRATEGY_BELOW_THRESHOLD",
    "STRATEGY_DISABLED",
    "STRATEGY_NO_RESOLVED_EPISODES",
    "STRATEGY_NO_UNRESOLVED_EPISODES",
    "STRATEGY_PROMPT_VERSION",
    "STRATEGY_RECALL_HEADER",
    "STRATEGY_RECALL_OPERATOR_EDITS",
    "STRATEGY_RECALL_SECTION",
    "STRATEGY_SECTION_TITLES",
    "STRATEGY_SYNTHESIS_EPISODE",
    "STRATEGY_SYNTHESIS_FAILED",
    "STRATEGY_SYNTHESIS_REQUEST",
    "STRATEGY_SYNTHESIS_SYSTEM_PROMPT",
]

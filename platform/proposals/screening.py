"""The gate every proposal passes before it becomes something a person can approve.

Two questions, asked at ``propose`` time and never at review time.

**Can this be reviewed at all?** A proposal states what would change — that is
the payload, and it is required by construction. It must also state *why*, *what
evidence*, and *which investigation*. Those three are what distinguish a
proposal from an assertion, and a queue that accepted proposals without them
would be a queue whose rows are all approved, because there is nothing in a row
to disagree with.

**Does it name something sealed?** Two kinds. The sections that decide what the
agent may do — masking, guardrail mode, what needs approval, how much autonomy —
and anything credential-shaped. Both are refused where the proposal is made, so
nothing sealed reaches a queue, a screen, or a tired person on a Friday.

The credential half is deliberately the same rule the configuration write path
enforces, reached through a structural protocol rather than an import: this
package sits below the configuration service, and a second implementation of
"what counts as a secret" would agree with the first until the day a vendor
schema changed.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from config.constants.proposals import SEALED_CONFIG_PREFIXES, SEALED_FIELD_NAMES
from platform.guardrails.engine import GuardrailEngine
from platform.proposals.errors import ProposalRefused
from platform.proposals.models import AgentProposal

#: Field names whose value is a *reference* by construction. Scanning one with
#: its own name attached reads as a secret behind a label — and the label is the
#: field that exists precisely so the secret is somewhere else. Mirrors the
#: configuration validator's list of the same name, for the same reason.
REFERENCE_FIELD_NAMES: frozenset[str] = frozenset({"credential"})

#: What a value is handed to the guardrail engine as. The field's own name is
#: included so the labelled rules fire the way they would on the line an agent
#: copied the value from.
_SCAN_TEMPLATE = "{label} = {value}"


@runtime_checkable
class SecretFields(Protocol):
    """Whatever can say which field names the installed integrations call secret.

    Structural, so the configuration validator satisfies it without either
    package importing the other. Optional at every call site: a deployment with
    no integration directory still has the sealed names below and the guardrail
    engine, which is less than the full rule but never more permissive than it.
    """

    def secret_field_names(self) -> frozenset[str]:
        """Return every field name an installed integration's schema calls secret."""


def screen(
    proposal: AgentProposal,
    *,
    credentials: SecretFields | None = None,
    guardrails: GuardrailEngine | None = None,
) -> None:
    """Raise ``ProposalRefused`` unless ``proposal`` may enter the queue."""
    _check_reviewable(proposal)
    _check_sealed_paths(proposal)
    _check_sealed_names(proposal, credentials)
    _check_credential_values(proposal, guardrails)


def _check_reviewable(proposal: AgentProposal) -> None:
    """Refuse a proposal missing any of the three things a review reads."""
    if not proposal.rationale.strip():
        raise ProposalRefused(
            proposal.proposal_id,
            "carries no rationale. A proposal states why the change is right, and one "
            "that does not is approved on the strength of nobody disagreeing with it.",
        )
    if not any(item.strip() for item in proposal.evidence):
        raise ProposalRefused(
            proposal.proposal_id,
            "carries no evidence. Name what you observed — the turns, the readings, the "
            "earlier runs — so a reviewer can check the conclusion rather than accept it.",
        )
    if not proposal.run_id.strip():
        raise ProposalRefused(
            proposal.proposal_id,
            "does not name the investigation that produced it. The link back to the run "
            "is what a reviewer follows, and a proposal with no origin cannot be checked.",
        )


def _check_sealed_paths(proposal: AgentProposal) -> None:
    """Refuse a payload naming any part of what constrains the agent."""
    for path, _ in _leaves(proposal.payload):
        for sealed in SEALED_CONFIG_PREFIXES:
            if path == sealed or path.startswith(f"{sealed}."):
                raise ProposalRefused(
                    proposal.proposal_id,
                    f"names {path!r}, which is under {sealed!r} — the configuration that "
                    f"decides what an agent is allowed to do. Nothing proposes a change to "
                    f"its own containment; ask a person to make this one directly.",
                )


def _check_sealed_names(proposal: AgentProposal, credentials: SecretFields | None) -> None:
    """Refuse a payload carrying a field somebody's schema marks secret."""
    sealed = SEALED_FIELD_NAMES | (
        credentials.secret_field_names() if credentials is not None else frozenset()
    )
    for path, _ in _leaves(proposal.payload):
        leaf = path.rpartition(".")[2]
        if leaf in sealed:
            raise ProposalRefused(
                proposal.proposal_id,
                f"sets {leaf!r} at {path!r}, which is a credential field. Configuration "
                f"holds references, never secrets, and a credential is never proposable: "
                f"store it in the vault and reference it there.",
            )


def _check_credential_values(proposal: AgentProposal, guardrails: GuardrailEngine | None) -> None:
    """Refuse a payload whose value looks like a credential, without quoting it."""
    if guardrails is None:
        return
    for path, value in _leaves(proposal.payload):
        if not isinstance(value, str) or not value:
            continue
        leaf = path.rpartition(".")[2]
        text = (
            value
            if leaf in REFERENCE_FIELD_NAMES
            else _SCAN_TEMPLATE.format(label=leaf, value=value)
        )
        result = guardrails.scan(text)
        if not result.clean:
            raise ProposalRefused(
                proposal.proposal_id,
                f"carries something matching the {result.rules_fired[0]!r} secret shape at "
                f"{path!r}. The matched text is not reproduced here.",
            )


def _leaves(values: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield every ``(dotted path, scalar)`` in ``values``, walking into lists.

    A walker of its own rather than the configuration service's, which does the
    same thing: importing that package from here would close a loop through the
    knowledge base, and ten lines is cheaper than a fragile import order. A list
    entry is addressed by index, so a sealed field in the third detector of a
    proposed set is found where it is.

    An **empty** section or list is a leaf. It has no scalar under it and it is
    still a change: ``policies.autonomy.statements = []`` revokes every autonomy
    statement a team has, and a walk that only yielded scalars would let the most
    destructive form of a sealed edit through as the one with nothing in it.
    """
    if isinstance(values, Mapping) and values:
        for name, value in values.items():
            yield from _leaves(value, f"{prefix}.{name}" if prefix else str(name))
    elif isinstance(values, Sequence) and not isinstance(values, str | bytes) and values:
        for index, value in enumerate(values):
            yield from _leaves(value, f"{prefix}.{index}" if prefix else str(index))
    else:
        yield prefix, values


__all__ = ["REFERENCE_FIELD_NAMES", "SecretFields", "screen"]

"""Every capability a run executes is attributable to the principal that caused it.

The attribution rides on ``TeamContext`` — the one value every stage already
holds — rather than being threaded as a second parameter. That is the property
worth testing: not that the fields exist, but that they reach the trace without
any stage having to remember to put them there, and that they survive the
round trip a resumed session makes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.state.agent_state import AgentState
from core.state.types import TeamContext
from platform.identity.models import Principal
from platform.persistence.ports import PrincipalKind

AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
ORG = "acme"


def state(team: TeamContext) -> AgentState:
    """Return a state for ``team`` with nothing else set."""
    return AgentState(run_id="run-1", team=team, started_at=AT)


def test_a_run_with_no_principal_says_so_rather_than_inventing_one() -> None:
    """A scheduled sweep has no human behind it, and the trace should admit it."""
    unattributed = TeamContext(team_id="payments")

    assert not unattributed.is_attributed
    assert unattributed.actor_id == ""
    assert unattributed.actor_kind == ""


def test_a_human_principal_becomes_the_run_s_attribution() -> None:
    """The wiring a transport does, asserted so its shape is fixed."""
    ada = Principal(principal_id="ada", org_id=ORG, display_name="Ada")
    team = TeamContext(
        team_id="payments", actor_id=ada.principal_id, actor_kind=ada.actor_kind.value
    )

    assert team.is_attributed
    assert team.actor_id == "ada"
    assert team.actor_kind == "user"


def test_a_token_principal_is_recorded_as_a_token_and_keeps_its_owner() -> None:
    """ "The payments bot did this" is not something anybody can follow up on."""
    bot = Principal(
        principal_id="ada",
        org_id=ORG,
        kind=PrincipalKind.SERVICE_ACCOUNT,
        display_name="payments bot",
        token_id="tok-1",
    )
    team = TeamContext(
        team_id="payments", actor_id=bot.principal_id, actor_kind=bot.actor_kind.value
    )

    assert team.actor_id == "ada", "the owning human, so somebody can be asked"
    assert team.actor_kind == "token", "and the fact that a machine presented it"


def test_the_attribution_reaches_the_trace_without_a_stage_touching_it() -> None:
    """The state serialises the whole context, so nothing has to remember to."""
    recorded = state(TeamContext(team_id="payments", actor_id="ada", actor_kind="user")).to_record()

    assert recorded["team"]["actor_id"] == "ada"
    assert recorded["team"]["actor_kind"] == "user"


def test_the_attribution_survives_a_resumed_session() -> None:
    """A run reloaded from storage is still attributable to the same principal."""
    original = state(TeamContext(team_id="payments", actor_id="ada", actor_kind="user"))
    resumed = AgentState.from_record(original.to_record())

    assert resumed.team.actor_id == "ada"
    assert resumed.team.actor_kind == "user"
    assert resumed.team == original.team


def test_a_record_written_before_attribution_existed_still_loads() -> None:
    """A rolling deployment reads sessions its predecessor wrote.

    Absent fields read as unattributed rather than raising, which is the same
    answer a run with no principal gets — and the correct one, because a session
    stored before this existed genuinely does not record who started it.
    """
    old = {
        "team_id": "payments",
        "integrations": ["datadog"],
        "sandbox_profiles": [],
        "destinations": [],
        "tool_budget": 8,
    }
    loaded = TeamContext.from_record(old)

    assert loaded.team_id == "payments"
    assert not loaded.is_attributed

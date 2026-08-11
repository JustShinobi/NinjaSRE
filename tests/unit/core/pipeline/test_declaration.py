"""The stage declaration is complete, ordered, and derived where it can be."""

from __future__ import annotations

from core.pipeline.declaration import PIPELINE_STAGES, declaration_for, stage_declarations
from core.pipeline.ownership import STAGE_WRITES
from core.state.types import STAGE_ORDER, StageName


def test_every_stage_is_declared_exactly_once() -> None:
    declared = [entry.name for entry in PIPELINE_STAGES]
    assert declared == list(STAGE_ORDER)


def test_the_order_is_the_pipeline_s_own() -> None:
    assert [entry.order for entry in stage_declarations()] == list(range(len(STAGE_ORDER)))


def test_what_a_stage_writes_is_read_from_the_ownership_table() -> None:
    for entry in PIPELINE_STAGES:
        assert set(entry.writes) == STAGE_WRITES[entry.name]


def test_every_stage_says_what_it_consults() -> None:
    for entry in PIPELINE_STAGES:
        assert entry.consults, f"{entry.name} declares nothing it consults"
        assert entry.summary


def test_a_stage_that_makes_no_model_call_names_no_role() -> None:
    # The shortlist is deterministic arithmetic on purpose, and a screen that
    # showed it running on a model role would be claiming a call nobody makes.
    assert declaration_for(StageName.PLAN_EVIDENCE).model_role == ""
    assert declaration_for(StageName.INTAKE).model_role == "intake"
    assert declaration_for(StageName.DIAGNOSE).model_role == "diagnose"


def test_only_the_gathering_stage_dispatches_specialists() -> None:
    dispatching = [entry.name for entry in PIPELINE_STAGES if entry.dispatches_subagents]
    assert dispatching == [StageName.GATHER_EVIDENCE]


def test_a_declared_role_is_one_the_configuration_binds() -> None:
    from config.constants.config_service import MODEL_ROLES

    for entry in PIPELINE_STAGES:
        assert entry.model_role == "" or entry.model_role in MODEL_ROLES

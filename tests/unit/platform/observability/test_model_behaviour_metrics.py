"""Counting what a model costs an operator in attempts, per model.

A model that needs three corrections a turn and one that needs none produce the
same investigations at very different cost, and the difference is invisible in a
run's wall clock. These are the numbers that make it visible — and they are
labelled by model precisely so an operator can put two models side by side and
see that changing would double their throughput.
"""

from __future__ import annotations

import pytest

from config.constants.llm import PROVIDER_OLLAMA
from core.agent.turn import GuardrailAction, GuardrailActionKind, Turn
from core.llm.types import Repair, RepairKind
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.metrics.definitions import (
    DEFINITIONS,
    MetricFamily,
    MetricRegistry,
)
from platform.observability.metrics.model_behaviour import (
    ModelBehaviourRecorder,
    record_turn,
)

pytestmark = pytest.mark.unit

MODEL = "qwen2.5:7b"


def _registry() -> MetricRegistry:
    config = TelemetryConfig(endpoint="http://collector.internal:4318")
    return MetricRegistry(config=config, exporter=OtlpExporter(config, RecordingTransport()))


class TestTheInstrumentsAreDeclared:
    def test_the_family_covers_everything_the_feature_promises_to_show(self) -> None:
        declared = {
            definition.name for definition in DEFINITIONS if definition.family is MetricFamily.MODEL
        }

        assert declared == {
            "model.repairs",
            "model.degradations",
            "model.loop_breaks",
            "model.compactions",
            "model.truncations",
        }

    def test_every_one_of_them_is_labelled_by_model(self) -> None:
        for definition in DEFINITIONS:
            if definition.family is MetricFamily.MODEL:
                assert "model" in definition.labels.names
                assert "provider" in definition.labels.names


class TestRecordingARepair:
    def test_a_repair_is_counted_against_the_model_that_needed_it(self) -> None:
        metrics = _registry()
        recorder = ModelBehaviourRecorder(metrics=metrics)

        recorder.record_repair(
            Repair(kind=RepairKind.UNKNOWN_ARGUMENT_REJECTED, capability="kubernetes_list_pods"),
            provider_id=PROVIDER_OLLAMA,
            model_id=MODEL,
        )

        assert (
            metrics.counter("model.repairs").value(
                model=MODEL,
                provider=PROVIDER_OLLAMA,
                kind=RepairKind.UNKNOWN_ARGUMENT_REJECTED.value,
            )
            == 1.0
        )

    def test_a_broken_loop_is_counted_as_its_own_number(self) -> None:
        metrics = _registry()
        recorder = ModelBehaviourRecorder(metrics=metrics)

        recorder.record_repair(
            Repair(kind=RepairKind.REPETITION_BROKEN, capability="prometheus_query"),
            provider_id=PROVIDER_OLLAMA,
            model_id=MODEL,
        )

        assert (
            metrics.counter("model.loop_breaks").value(model=MODEL, provider=PROVIDER_OLLAMA) == 1.0
        )

    def test_a_degraded_run_is_counted_by_its_cause(self) -> None:
        metrics = _registry()
        recorder = ModelBehaviourRecorder(metrics=metrics)

        recorder.record_degradation(
            "repair_budget_exhausted", provider_id=PROVIDER_OLLAMA, model_id=MODEL
        )

        assert (
            metrics.counter("model.degradations").value(
                model=MODEL, provider=PROVIDER_OLLAMA, kind="repair_budget_exhausted"
            )
            == 1.0
        )

    def test_a_deployment_with_telemetry_off_still_accepts_every_write(self) -> None:
        config = TelemetryConfig()
        metrics = MetricRegistry(config=config, exporter=OtlpExporter(config, RecordingTransport()))
        recorder = ModelBehaviourRecorder(metrics=metrics)

        recorder.record_repair(
            Repair(kind=RepairKind.TOOL_CALL_EXTRACTED),
            provider_id=PROVIDER_OLLAMA,
            model_id=MODEL,
        )

        assert metrics.snapshot() == []


class TestRecordingWhatATurnDid:
    def test_a_compaction_and_a_truncation_are_both_counted(self) -> None:
        metrics = _registry()
        turn = Turn(
            index=1,
            provider_id=PROVIDER_OLLAMA,
            model_id=MODEL,
            guardrail_actions=(
                GuardrailAction(kind=GuardrailActionKind.TRANSCRIPT_COMPACTED, target="s1"),
                GuardrailAction(kind=GuardrailActionKind.RESULT_TRUNCATED, target="read_logs"),
                GuardrailAction(kind=GuardrailActionKind.RESULT_TRUNCATED, target="read_logs"),
            ),
        )

        record_turn(metrics, turn)

        labels = {"model": MODEL, "provider": PROVIDER_OLLAMA}
        assert metrics.counter("model.compactions").value(**labels) == 1.0
        assert metrics.counter("model.truncations").value(**labels) == 2.0

    def test_a_turn_that_needed_nothing_writes_nothing(self) -> None:
        metrics = _registry()

        record_turn(metrics, Turn(index=1, provider_id=PROVIDER_OLLAMA, model_id=MODEL))

        assert metrics.snapshot() == []

    def test_a_repaired_turn_counts_the_repair_from_the_trace(self) -> None:
        metrics = _registry()
        turn = Turn(
            index=1,
            provider_id=PROVIDER_OLLAMA,
            model_id=MODEL,
            guardrail_actions=(
                GuardrailAction(
                    kind=GuardrailActionKind.MODEL_OUTPUT_REPAIRED,
                    target="kubernetes_list_pods",
                    reason=f"{RepairKind.TOOL_CALL_EXTRACTED.value}: wrote it as text",
                ),
            ),
        )

        record_turn(metrics, turn)

        assert (
            metrics.counter("model.repairs").value(
                model=MODEL,
                provider=PROVIDER_OLLAMA,
                kind=RepairKind.TOOL_CALL_EXTRACTED.value,
            )
            == 1.0
        )

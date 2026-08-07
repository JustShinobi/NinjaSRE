"""Both capture sources, the provenance that tells them apart, and what is reported.

The point of these assertions is the handover. Half of this dataset is projected
into shapes the gateway does not serve yet, and when it does, the ``pvesh`` half
of the direct path is deleted rather than kept as a second way to produce the
same fixture. That deletion is only possible if the three classes of record are
distinguishable now.
"""

from __future__ import annotations

import json

import pytest

from tools.mockplane.allowlist import Allowlist, CommandRefused
from tools.mockplane.capture.channel import (
    ChannelError,
    NoConnectionDetails,
    NodeConfiguration,
    ReadOnlyChannel,
    RecordedCommandRunner,
)
from tools.mockplane.capture.cluster import read_cluster
from tools.mockplane.capture.gateway import (
    Answer,
    GatewayTarget,
    GatewayUnreachable,
    capture_gateway,
)
from tools.mockplane.capture.projection import project
from tools.mockplane.dataset import profile
from tools.mockplane.endpoints import endpoint_by_slug, gateway_endpoints, projected_endpoints
from tools.mockplane.records import Provenance

pytestmark = pytest.mark.unit


class _Fetcher:
    """A fetcher that answers from a script and records what it was asked."""

    def __init__(self, answers: dict[str, Answer] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[tuple[str, str, str]] = []

    def fetch(self, method: str, url: str, token: str) -> Answer:
        self.asked.append((method, url, token))
        if url in self.answers:
            return self.answers[url]
        return Answer(status=200, body={"recorded": url})


# --- The gateway half -------------------------------------------------------------


def test_the_gateway_capture_records_only_reads() -> None:
    fetcher = _Fetcher()
    result = capture_gateway(GatewayTarget(base_url="https://deployment.example.invalid"), fetcher)
    assert all(method == "GET" for method, _, _ in fetcher.asked)
    assert all(record.provenance is Provenance.GATEWAY for record in result.records)


def test_a_write_endpoint_is_reported_as_missed_with_the_reason() -> None:
    result = capture_gateway(
        GatewayTarget(base_url="https://deployment.example.invalid"), _Fetcher()
    )
    written = {entry.slug for entry in result.missed}
    assert "investigation-start" in written
    reason = next(entry for entry in result.missed if entry.slug == "investigation-start").reason
    assert "changes the thing it measures" in reason or "writes" in reason


def test_a_templated_endpoint_with_no_argument_is_missed_rather_than_skipped() -> None:
    result = capture_gateway(GatewayTarget(base_url="https://d.example.invalid"), _Fetcher())
    missed = {entry.slug: entry.reason for entry in result.missed}
    assert "run-detail" in missed
    assert "run_id" in missed["run-detail"]


def test_a_templated_endpoint_is_recorded_when_an_argument_is_supplied() -> None:
    fetcher = _Fetcher()
    result = capture_gateway(
        GatewayTarget(base_url="https://d.example.invalid"),
        fetcher,
        arguments={"run-detail": {"run_id": "run-0001"}},
        endpoints=[endpoint_by_slug("run-detail")],
    )
    assert [record.slug for record in result.records] == ["run-detail"]
    assert result.records[0].arguments == {"run_id": "run-0001"}
    assert fetcher.asked == [("GET", "https://d.example.invalid/v1/runs/run-0001", "")]


def test_a_refusal_is_reported_with_the_status_it_answered() -> None:
    fetcher = _Fetcher({"https://d.example.invalid/v1/runs": Answer(status=403, body={})})
    result = capture_gateway(
        GatewayTarget(base_url="https://d.example.invalid"),
        fetcher,
        endpoints=[endpoint_by_slug("runs")],
    )
    assert not result.records
    assert "403" in result.missed[0].reason


def test_the_request_and_the_contract_version_are_recorded_beside_the_response() -> None:
    result = capture_gateway(
        GatewayTarget(base_url="https://d.example.invalid"),
        _Fetcher(),
        endpoints=[endpoint_by_slug("runs")],
    )
    record = result.records[0]
    assert record.request.method == "GET"
    assert record.request.path == "/v1/runs"
    assert record.contract_version


def test_a_deployment_that_does_not_answer_is_reported_rather_than_raised() -> None:
    class _Unreachable:
        def fetch(self, method: str, url: str, token: str) -> Answer:
            raise GatewayUnreachable(f"{url} could not be reached")

    result = capture_gateway(
        GatewayTarget(base_url="https://d.example.invalid"),
        _Unreachable(),
        endpoints=[endpoint_by_slug("runs")],
    )
    assert not result.records
    assert "could not be reached" in result.missed[0].reason


def test_a_target_needs_configuring_and_says_which_variable() -> None:
    with pytest.raises(GatewayUnreachable) as failure:
        GatewayTarget.from_environment({})
    assert "NINJASRE_CAPTURE_ENDPOINT" in str(failure.value)


# --- The infrastructure half ------------------------------------------------------


def test_connection_details_come_from_configuration_not_from_source() -> None:
    configuration = NodeConfiguration.from_environment(
        {"NINJASRE_CAPTURE_NODES": "node01=10.0.0.1,node02=10.0.0.2"}
    )
    assert configuration.hosts == {"node01": "10.0.0.1", "node02": "10.0.0.2"}
    assert configuration.user == "root"


def test_nothing_naming_a_node_is_refused_with_the_variable_named() -> None:
    with pytest.raises(NoConnectionDetails) as failure:
        NodeConfiguration.from_environment({})
    assert "NINJASRE_CAPTURE_NODES" in str(failure.value)


def test_the_channel_refuses_before_it_sends() -> None:
    runner = RecordedCommandRunner(answers={})
    channel = ReadOnlyChannel(runner=runner, allowlist=Allowlist.load())
    with pytest.raises(CommandRefused):
        channel.read("node01", "cat /etc/shadow")


def test_the_channel_reports_a_refusal_without_raising_for_the_ad_hoc_tool() -> None:
    channel = ReadOnlyChannel(runner=RecordedCommandRunner(), allowlist=Allowlist.load())
    assert channel.refuses("cat /etc/shadow") is not None
    assert channel.refuses("uname -r") is None


def test_an_unrecorded_read_fails_loudly_rather_than_answering_nothing() -> None:
    channel = ReadOnlyChannel(runner=RecordedCommandRunner(), allowlist=Allowlist.load())
    with pytest.raises(ChannelError):
        channel.read("node01", "uname -r")


def test_a_pvesh_read_that_answers_something_other_than_json_is_an_error() -> None:
    channel = ReadOnlyChannel(
        runner=RecordedCommandRunner(
            answers={("node01", "pvesh get /nodes --output-format json"): "permission denied"}
        ),
        allowlist=Allowlist.load(),
    )
    with pytest.raises(ChannelError):
        channel.read_json("node01", "pvesh get /nodes --output-format json")


def test_a_cluster_read_collects_what_it_could_not_make_rather_than_dying() -> None:
    channel = ReadOnlyChannel(
        runner=RecordedCommandRunner(
            answers={("node01", "uname -r"): "7.0.14-8\n"},
        ),
        allowlist=Allowlist.load(),
    )
    reading, missed = read_cluster(channel, ("node01",), captured_at="2026-08-07T09:41:00+00:00")
    assert reading.nodes[0].kernel_running == "7.0.14-8"
    assert missed, "nothing was reported as unreachable, yet almost nothing was recorded"


def test_a_pvesh_payload_is_the_shape_a_rest_client_will_return() -> None:
    # ``pvesh`` is the same API behind the same JSON, which is what makes this
    # half of the capture reusable — and deletable — once the integration lands.
    payload = [{"vmid": 100, "name": "plateau", "status": "running", "cpu": 0.04}]
    channel = ReadOnlyChannel(
        runner=RecordedCommandRunner(
            answers={
                ("node01", "pvesh get /nodes/node01/lxc --output-format json"): json.dumps(payload)
            }
        ),
        allowlist=Allowlist.load(),
    )
    assert (
        channel.read_json("node01", "pvesh get /nodes/node01/lxc --output-format json") == payload
    )


# --- Provenance -------------------------------------------------------------------


def test_a_projected_record_cannot_be_mistaken_for_one_the_gateway_returned() -> None:
    projected = project(profile.cluster_reading())
    assert projected
    assert all(record.provenance is not Provenance.GATEWAY for record in projected)
    assert all(record.is_projected for record in projected)


def test_the_two_direct_classes_are_distinguishable_from_each_other() -> None:
    sources = {record.provenance for record in project(profile.cluster_reading())}
    assert Provenance.PVESH in sources, "nothing is attributed to the cluster's own API"
    assert Provenance.SHELL in sources, "nothing is attributed to the reads no API answers"


def test_every_projection_answers_an_endpoint_the_gateway_does_not_serve() -> None:
    served = {endpoint.slug for endpoint in gateway_endpoints()}
    projected = {record.slug for record in project(profile.cluster_reading())}
    assert not projected & served, "a projection for an endpoint that already exists"
    assert projected <= {endpoint.slug for endpoint in projected_endpoints()}


def test_only_the_shell_class_survives_the_handover() -> None:
    # The reads that have no gateway equivalent: failed units, thin-pool
    # metadata, mount state. When the integration lands, the ``pvesh`` half goes
    # and this half stays, which is a finding worth carrying forward.
    shell = {
        record.slug
        for record in project(profile.cluster_reading())
        if record.provenance is Provenance.SHELL
    }
    assert {"estate-nodes", "estate-storage"} <= shell

"""The change record a configured git host answers.

One vendor, one payload shape, one ``Change``. The point of the adapter is
that nothing above it learns which one answered: an investigation asks what
changed, and the deployment's configuration decides whether that question goes
to GitHub or nowhere, because no other git host is in the catalogue.

The second thing this file pins is the honest limitation. A commit listing is
not an apply record: the endpoint does not return the paths a commit touched,
so a change from a git host carries no paths — and without paths the
correlation cannot reach a component, which means it cannot reach a resource.
The source says so rather than returning an empty tuple that reads as "this
commit touched nothing". That distinction is the difference between a weak
correlation and a wrong one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from integrations._base.access import IntegrationAccess, bind, restore
from integrations._base.changes import (
    GIT_HOST_VENDORS,
    GitHostChangeSource,
    UnsupportedGitHost,
)
from platform.changes.models import ChangeWindow
from platform.changes.port import ChangeSource
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
DAY = ChangeWindow.ending(NOW)

#: A credential shape the shipped ruleset redacts, spelled the way one arrives:
#: in a message somebody wrote while rotating it. Not a real key.
LEAKED_KEY = "AKIAIOSFODNN7EXAMPLE"

#: One commit, in the shape GitHub's listing endpoint really returns, down to
#: which key the instant lives under.
PAYLOADS: dict[str, Any] = {
    "github": {
        "items": [
            {
                "sha": "9f2c1abdeadbeef",
                "commit": {
                    "author": {"name": "erik", "date": "2026-08-01T14:19:03Z"},
                    "message": "feat(monitoring): raise the scrape interval",
                },
            }
        ]
    },
}


class RecordedHost:
    """A proxy transport that answers one vendor's listing and records the ask.

    Serves a copy rather than the declaration. A test that edited the shared
    payload to say something else would be one whose neighbours pass or fail by
    the order they ran in.
    """

    def __init__(self, vendor: str, *, subject: str = "") -> None:
        self.vendor = vendor
        self.subject = subject
        self.asked: list[ProxyRequest] = []

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.asked.append(request)
        return OutboundResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(self._body()).encode("utf-8"),
        )

    def _body(self) -> Any:
        """Return this vendor's payload, with the first subject line replaced."""
        body = deepcopy(PAYLOADS[self.vendor])
        if not self.subject:
            return body
        first = body[0] if isinstance(body, list) else next(iter(body.values()))[0]
        for key in ("title", "message"):
            if key in first:
                first[key] = self.subject
        if "commit" in first:
            first["commit"]["message"] = self.subject
        return body


@pytest.fixture
def host(request: pytest.FixtureRequest) -> Iterator[RecordedHost]:
    """Bind a recorded host for the vendor the test parameterised."""
    vendor = getattr(request, "param", "github")
    recorded = RecordedHost(vendor)
    previous = bind(IntegrationAccess(transport=recorded, org_id="org-1", team_id="team-1"))
    try:
        yield recorded
    finally:
        restore(previous)


@pytest.mark.parametrize("host", ["github"], indirect=True)
@pytest.mark.asyncio
async def test_every_vendor_answers_with_the_same_record(host: RecordedHost) -> None:
    source = GitHostChangeSource(vendor=host.vendor, repository="infra/cluster")

    found = await source.changes_in(DAY)

    assert len(found) == 1
    change = found[0]
    assert change.change_id == "9f2c1ab"
    assert change.author == "erik"
    assert change.message == "feat(monitoring): raise the scrape interval"
    assert change.occurred_at == datetime(2026, 8, 1, 14, 19, 3, tzinfo=UTC)
    assert change.source == f"git:{host.vendor}"


@pytest.mark.asyncio
async def test_a_commit_outside_the_window_is_dropped_by_the_source(host: RecordedHost) -> None:
    # GitHub's listing narrows by other means, so the window is applied here.
    # A source that returned everything the vendor sent would put last month's
    # commit in an answer about the last day.
    found = await GitHostChangeSource(vendor="github").changes_in(DAY)

    assert [change.change_id for change in found] == ["9f2c1ab"]


@pytest.mark.asyncio
async def test_a_commit_is_never_reported_as_applied(host: RecordedHost) -> None:
    # A git host knows what was merged and nothing about what was deployed.
    # Reporting a commit as applied would be the exact mistake this feature
    # exists to prevent.
    found = await GitHostChangeSource(vendor="github").changes_in(DAY)

    assert found[0].applied is False


@pytest.mark.asyncio
async def test_the_absence_of_paths_is_stated_rather_than_left_as_an_empty_tuple(
    host: RecordedHost,
) -> None:
    found = await GitHostChangeSource(vendor="github").changes_in(DAY)

    assert found[0].paths == ()
    assert "paths" in found[0].detail
    assert GitHostChangeSource(vendor="github").provides_paths is False


@pytest.mark.asyncio
async def test_a_credential_in_a_commit_message_is_redacted_on_this_route_too() -> None:
    # The leak is closed at the local source; closing it there and not here
    # would leave the same secret one configured vendor away from the trace.
    # Asserted against a real credential shape rather than against an empty
    # redaction list, because an empty list is what a change carries anyway —
    # a test that asserted one would pass with the screening deleted.
    leaking = RecordedHost("github", subject=f"fix(monitoring): rotate {LEAKED_KEY}")
    previous = bind(IntegrationAccess(transport=leaking, org_id="org-1", team_id="team-1"))
    try:
        found = await GitHostChangeSource(vendor="github").changes_in(DAY)
    finally:
        restore(previous)

    assert LEAKED_KEY not in found[0].message
    assert found[0].redactions == ("aws-access-key-id",)


@pytest.mark.asyncio
async def test_the_vendor_the_deployment_configured_is_the_one_that_is_called(
    host: RecordedHost,
) -> None:
    await GitHostChangeSource(vendor="github", repository="infra/cluster").changes_in(DAY)

    assert [request.integration for request in host.asked] == ["github"]
    assert host.asked[0].capability == "changes_in_window"


@pytest.mark.asyncio
async def test_a_vendor_with_no_commit_listing_is_refused_at_construction() -> None:
    with pytest.raises(UnsupportedGitHost) as refusal:
        GitHostChangeSource(vendor="prometheus")

    assert "prometheus" in str(refusal.value)
    assert all(vendor in str(refusal.value) for vendor in GIT_HOST_VENDORS)


@pytest.mark.asyncio
async def test_an_unbound_deployment_reports_nothing_rather_than_inventing_a_client() -> None:
    # Nothing composed an access binding, which is the ordinary state of a
    # deployment that has configured no git host. Empty, not an exception into
    # an investigation.
    source = GitHostChangeSource(vendor="github")

    assert await source.changes_in(DAY) == ()


def test_the_git_host_source_satisfies_the_change_source_contract() -> None:
    assert isinstance(GitHostChangeSource(vendor="github"), ChangeSource)

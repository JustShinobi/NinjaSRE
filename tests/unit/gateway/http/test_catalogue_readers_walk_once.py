"""One discovery walk per reader, however many names it is asked about.

``CatalogueView.of`` asks the reader for every name and then describes each
one, which is a hundred-odd calls. A reader that walked discovery on every
call — importing sixteen thousand modules and parsing every skill manifest
each time — answered ``GET /v1/config/{node}/catalogue`` in two seconds on
staging and, being synchronous, held the gateway's one event loop for the
whole of it. The walk is still per reader rather than per process: a reader
is built per request, so a capability added while the process runs is seen
by the next request, which is the property the reader's docstring promises.
"""

from __future__ import annotations

import pytest

from gateway.http import catalogue_readers
from gateway.http.catalogue_readers import installed_catalogue, installed_integrations
from platform.config_service.catalogue import CatalogueView, integration_forms
from platform.config_service.schema.root import RootConfig

pytestmark = pytest.mark.unit


def _counting(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    calls = [0]
    real = getattr(catalogue_readers, name)

    def counted() -> object:
        calls[0] += 1
        return real()

    monkeypatch.setattr(catalogue_readers, name, counted)
    return calls


def test_a_whole_catalogue_view_walks_capability_discovery_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _counting(monkeypatch, "discover_capabilities")

    view = CatalogueView.of(installed_catalogue(), RootConfig())

    assert len(view.entries) > 1
    assert calls[0] == 1


def test_a_whole_integration_form_set_walks_integration_discovery_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _counting(monkeypatch, "discover_integrations")

    forms = integration_forms(installed_integrations(), RootConfig())

    assert len(forms) > 1
    assert calls[0] == 1


def test_a_new_reader_walks_again_so_a_running_process_still_sees_additions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _counting(monkeypatch, "discover_capabilities")

    installed_catalogue().names()
    installed_catalogue().names()

    assert calls[0] == 2

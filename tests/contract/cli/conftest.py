"""A seeded in-memory deployment for the surfaces to be driven against."""

from __future__ import annotations

import pytest

from surfaces.cli.client import LocalClient, PlatformClient
from tests.support.deployment import FakeServices, seeded


@pytest.fixture
def services() -> FakeServices:
    """Return a seeded in-memory deployment."""
    return seeded()


@pytest.fixture
def client(services: FakeServices) -> PlatformClient:
    """Return a client over the seeded deployment."""
    return LocalClient(services=services)

"""A document carrying a secret is refused, and the refusal says where without saying what.

FR-015 asks for two things that pull against each other. The location has to be
specific enough for whoever pasted the credential to find it — a section and a
line, not "somewhere in the document". And the report must not reproduce the
matched text, because a refusal that echoed the secret would put it in the trace,
the log, and the console: three places it was being kept out of.

So the report carries the rule that fired, the section, the line, and the
character offsets. Never the match.
"""

from __future__ import annotations

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import IngestionOutcome, KnowledgeIngestor
from platform.knowledge.base.models import Document, DocumentType
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import PAYMENTS_TEAM, PRIMARY_ORG, Clock

pytestmark = pytest.mark.unit

#: A runbook whose recovery section carries a private key. The key material is
#: the shipped ruleset's ``private-key-block`` shape and nothing more — enough to
#: match, and not a real key.
RUNBOOK_WITH_A_SECRET = """# Payments recovery

Restart the deployment and wait for the readiness probe.

## Emergency access

Use the break-glass key:

-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAx
-----END RSA PRIVATE KEY-----
"""


def runbook(body: str) -> Document:
    """Return a payments runbook carrying ``body``."""
    return Document(
        document_id="payments-recovery",
        org_id=PRIMARY_ORG,
        team_node_id=PAYMENTS_TEAM,
        title="Payments recovery",
        body=body,
        document_type=DocumentType.RUNBOOK,
    )


async def test_a_document_containing_a_secret_is_rejected_with_its_location(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """SC-006."""
    ingestor = KnowledgeIngestor(
        gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
    )

    result = await ingestor.ingest(runbook(RUNBOOK_WITH_A_SECRET))

    assert result.outcome is IngestionOutcome.REJECTED
    assert result.rules_fired == ("private-key-block",)

    location = result.locations[0]
    assert location.rule == "private-key-block"
    assert location.section == "Emergency access"
    assert location.line == 9
    assert location.start < location.end

    # The refusal names the rule and the place, never the match.
    assert "PRIVATE KEY" not in result.reason
    assert "MIIEowIBAAKCAQEAx" not in result.reason


async def test_a_rejected_document_is_not_stored_at_all(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    # Not stored redacted, either. A runbook with a hole in it that nobody knows
    # about is worse than a refusal somebody has to act on.
    ingestor = KnowledgeIngestor(
        gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
    )

    await ingestor.ingest(runbook(RUNBOOK_WITH_A_SECRET))

    async with gateway.begin(scope) as uow:
        assert await uow.knowledge.get_document("payments-recovery") is None
        assert await uow.knowledge.count_chunks() == 0


async def test_a_clean_document_is_chunked_embedded_and_searchable(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    ingestor = KnowledgeIngestor(
        gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
    )

    result = await ingestor.ingest(
        runbook("# Payments recovery\n\nRestart the deployment and wait for readiness.\n")
    )

    assert result.outcome is IngestionOutcome.STORED
    assert result.chunks == 1

    async with gateway.begin(scope) as uow:
        assert await uow.knowledge.count_chunks() == 1
        stored = await uow.knowledge.get_document("payments-recovery")

    assert stored is not None
    assert stored.title == "Payments recovery"

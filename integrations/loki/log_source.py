"""Loki as the log source the observability bridge asks for.

``LogSource`` says what an investigation needs of a log system and ``LokiClient``
can query one. Nothing joined them, so a deployment with Loki configured and
reachable still answered every log question with "no source composed" — both
halves correct, and no adapter between them.

**Nanoseconds.** Loki's range endpoint takes and returns nanoseconds since the
epoch, as strings. Read as seconds every line lands in 1970; written as seconds
the query asks about it. Both failures are silent, because the window in the
answer still looks like the window that was asked for.

**Labels belong to the stream.** One ``values`` array comes back per stream with
the labels beside it, so a flattening pass that does not carry them down loses
which guest each line is about — which is the only thing making the line useful.

**A line that cannot be dated is dropped, not stamped with now.** Dating it now
makes a stale line look live, and that is the one misreading that changes what an
operator concludes.

**Nothing here imports the observability bridge.** The bridge is an optional
feature and an integration that imported it would make it mandatory — which is
what ``test_no_feature_beside_this_one_depends_on_the_bridge`` exists to prevent.
So this returns its own plain lines and raises the integration error every other
vendor client raises; the gateway's composition, which may depend on the bridge,
is where the two vocabularies meet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations.loki.schema import INTEGRATION
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Loki speaks nanoseconds since the epoch on the range endpoint, in both
#: directions.
NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True, slots=True)
class LogLine:
    """One line Loki returned, with the stream's labels carried onto it.

    This package's own type rather than the bridge's, so an optional feature
    stays optional. It is deliberately the same shape, and the composition that
    holds both converts one to the other in a single expression.
    """

    observed_at: datetime
    line: str
    labels: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class LokiQuery(Protocol):
    """Whatever can run one Loki range query."""

    async def search_logs(
        self,
        query: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = 0,
    ) -> Any:
        """Return the pages Loki answered with for ``query``."""


def _nanoseconds(moment: datetime) -> str:
    """Return ``moment`` as Loki spells an instant."""
    return str(int(moment.timestamp() * NANOSECONDS_PER_SECOND))


def lines_of(streams: Sequence[Mapping[str, Any]]) -> tuple[LogLine, ...]:
    """Flatten Loki's stream/values shape into lines that carry their labels."""
    found: list[LogLine] = []
    for stream in streams:
        labels = {str(name): str(value) for name, value in (stream.get("stream") or {}).items()}
        for entry in stream.get("values") or ():
            if not isinstance(entry, Sequence) or isinstance(entry, str) or len(entry) < 2:
                # A vendor's payload is not a schema this can rely on.
                continue
            try:
                stamp = int(entry[0])
            except (TypeError, ValueError):
                continue
            found.append(
                LogLine(
                    observed_at=datetime.fromtimestamp(stamp / NANOSECONDS_PER_SECOND, UTC),
                    line=str(entry[1]),
                    labels=labels,
                )
            )
    return tuple(found)


@dataclass(frozen=True, slots=True)
class LokiLogSource:
    """One Loki, answering the bridge's log questions."""

    client: LokiQuery

    async def retention_seconds(self) -> int:
        """Return zero: Loki publishes no retention over its HTTP API.

        Zero is the bridge's "it has no opinion", which is what makes the answer
        carry its own bound instead of implying a completeness nobody verified.
        """
        return 0

    async def lines(
        self,
        *,
        selector: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> tuple[LogLine, ...]:
        """Return up to ``limit`` lines matching ``selector`` in the window given."""
        try:
            pages = await self.client.search_logs(
                selector,
                start=_nanoseconds(start),
                end=_nanoseconds(end),
                limit=limit,
            )
        except Exception as failed:
            # Unreachable rather than empty: "nothing matched" and "we could not
            # ask" lead a responder to opposite conclusions.
            logger.warning("logs.source_unreachable", error=str(failed))
            raise IntegrationError(
                f"the log source did not answer: {failed}",
                integration=INTEGRATION,
                reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
            ) from failed

        return lines_of(tuple(getattr(pages, "items", ()) or ()))


__all__ = ["NANOSECONDS_PER_SECOND", "LokiLogSource", "LokiQuery", "lines_of"]

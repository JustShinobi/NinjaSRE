"""What each sink's readership is allowed to be told.

Redaction happens here, at the sink, rather than when the notification is built.
One notification with per-sink redaction means a private incident channel can see
what a public status page cannot, from one code path — and it means a change to
what a notification says cannot accidentally bypass redaction for one sink,
because there is no second place where the text is produced.

Two questions, answered separately because their answers differ.

**May this readership see the guardrail-filtered text?** Everything published
is filtered. There is no sink here that is local, so this half is unconditional.

**May this readership see masked identifiers put back?** Only a private one.
Restoration turns ``NSRE_MASK_POD_3`` back into a pod name, and a wide channel is
a place where filtering is wanted and restoration is not. A token left in place
is meaningless without the run's mapping, which is exactly what makes leaving it
the right answer rather than a degraded one.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.guardrails.sinks import Sink, SinkGuard
from platform.notifications.models import Notification
from platform.reporting.models import Audience


@dataclass(slots=True)
class SinkRedactor:
    """Renders text as one audience may read it.

    Holds the guard rather than a pre-redacted string, so nothing upstream has to
    remember to redact and nothing downstream can forget to. The guard carries
    the run's masking context when there is one; without it, restoration is a
    no-op and the tokens simply stay put.
    """

    guard: SinkGuard

    def render(self, text: str, *, audience: Audience) -> str:
        """Return ``text`` as ``audience`` may read it."""
        if not text:
            return text
        return self.guard.render(text, sink=Sink.REPORT, authorised=audience.restores_identifiers)

    def redact(self, notification: Notification, *, audience: Audience) -> Notification:
        """Return ``notification`` with its prose rendered for ``audience``.

        The link is not redacted. It is NinjaSRE's own address for the run, and
        somebody who cannot reach it learns nothing from it — while a reader who
        can is the reader the notification is for.
        """
        return notification.with_text(
            title=self.render(notification.title, audience=audience),
            message=self.render(notification.message, audience=audience),
        )


__all__ = ["SinkRedactor"]

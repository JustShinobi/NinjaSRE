"""End-to-end suites: a real application failing, and real cloud infrastructure.

Two halves, and they answer different questions.

``otel_demo``
    A microservice application with its own observability stack, failing because
    a feature flag says so. The value is that the telemetry is genuinely a
    distributed system's — traces that span services, logs nobody wrote for a
    test, metrics with real noise in them — and none of it was designed around
    the answer.
``cloud``
    Managed services, provisioned, exercised, and destroyed. The value is the
    integrations: a CloudWatch query against real CloudWatch is a different
    thing from one against a recording, and the difference shows up as a
    permission nobody granted or a shape nobody predicted.

``capture`` is what makes both affordable. The most valuable output of an
expensive suite is a cheap permanent test, so a real failure the agent missed is
turned into a synthetic scenario the fast suite runs on every change.
"""

from __future__ import annotations

"""Turning a demo fault on and off, which is a configuration patch either way.

The demo's faults are feature flags, so injection has none of the chaos suite's
apply-and-delete shape: the object already exists, and what changes is one
field. That makes the failure mode different too. A chaos object that was never
applied leaves nothing behind; a flag that was turned on and never turned off
leaves the demo broken for the next run, and looks exactly like a demo that was
broken to begin with.

So the same ledger discipline applies, in the shape a patch takes: the *restore*
is registered before the change is made, and it is applied on every way out —
including the ones that do not come back through this module.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from config.constants.chaos import OTEL_DEMO_FLAG_CONFIG
from tests.e2e.otel_demo.faults import DemoFault
from tests.support.commands import CommandFailed, CommandRunner

#: Where the flag document lives inside the configuration object.
FLAG_DOCUMENT_KEY = "demo.flagd.json"


class FlagError(RuntimeError):
    """A feature flag could not be read or written."""


@dataclass(slots=True)
class FlagdFaults:
    """Reads and writes the demo's feature flags through the cluster.

    Patches the configuration object rather than calling the flag service's own
    API. The service reads the object, so this is the same change from the
    demo's point of view — and it needs no port-forward, no credential, and no
    second thing to be running.
    """

    runner: CommandRunner
    namespace: str
    configuration: str = OTEL_DEMO_FLAG_CONFIG
    kubectl: str = "kubectl"
    #: Every restore this object owes, newest last. Written before the change.
    restores: list[tuple[str, str]] = field(default_factory=list)

    def _argv(self, *arguments: str) -> tuple[str, ...]:
        return (self.kubectl, "-n", self.namespace, *arguments)

    def read(self) -> dict[str, Any]:
        """Return the flag document as the demo currently holds it.

        Raises:
            FlagError: the object is missing or does not hold a flag document.
        """
        result = self.runner.run(
            self._argv(
                "get",
                "configmap",
                self.configuration,
                "-o",
                f"jsonpath={{.data['{FLAG_DOCUMENT_KEY.replace('.', chr(92) + '.')}']}}",
            )
        )
        if not result.ok:
            raise FlagError(
                f"the demo's flag configuration {self.configuration!r} could not be read in "
                f"{self.namespace!r}: {result.message}"
            )
        try:
            document = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as failure:
            raise FlagError(
                f"{self.configuration}: {FLAG_DOCUMENT_KEY} is not JSON ({failure})"
            ) from failure
        return document if isinstance(document, dict) else {}

    def variant_of(self, flag: str) -> str:
        """Return the variant ``flag`` currently serves."""
        flags = self.read().get("flags")
        entry = flags.get(flag) if isinstance(flags, Mapping) else None
        return str(entry.get("defaultVariant", "")) if isinstance(entry, Mapping) else ""

    def set_variant(self, flag: str, variant: str) -> None:
        """Make ``flag`` serve ``variant``.

        Raises:
            FlagError: the cluster refused the patch.
        """
        document = self.read()
        flags = document.get("flags")
        if not isinstance(flags, Mapping) or flag not in flags:
            raise FlagError(
                f"the demo declares no flag called {flag!r}; a fault naming one that does not "
                f"exist would run, change nothing, and be scored"
            )
        updated = {**document, "flags": {**flags, flag: {**flags[flag], "defaultVariant": variant}}}
        patch = json.dumps({"data": {FLAG_DOCUMENT_KEY: json.dumps(updated)}})
        result = self.runner.run(
            self._argv("patch", "configmap", self.configuration, "--type", "merge", "-p", patch)
        )
        if not result.ok:
            raise FlagError(f"{flag}: the cluster refused the patch ({result.message})")

    def restore_all(self) -> tuple[str, ...]:
        """Put every flag this object changed back, and return which ones.

        Never raises. A restore that failed must not stop the rest of the
        restores, for the same reason a failed deletion must not stop cleanup.
        """
        restored: list[str] = []
        for flag, variant in reversed(self.restores):
            try:
                self.set_variant(flag, variant)
            except (FlagError, CommandFailed):
                continue
            restored.append(flag)
        self.restores = []
        return tuple(restored)


@contextmanager
def injected(faults: FlagdFaults, fault: DemoFault) -> Iterator[DemoFault]:
    """Turn ``fault`` on for the duration of the block and off on every way out."""
    before = faults.variant_of(fault.flag) or fault.off_variant
    faults.restores.append((fault.flag, before))
    try:
        faults.set_variant(fault.flag, fault.variant)
        yield fault
    finally:
        faults.restore_all()


__all__ = ["FLAG_DOCUMENT_KEY", "FlagError", "FlagdFaults", "injected"]

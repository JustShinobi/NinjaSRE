"""The scenario harness: fixtures in, an investigation out, a verdict recorded.

Everything the evaluation half of the product stands on lives here, and it
lives beside the tests rather than inside a package tier on purpose. A harness
is not something a deployment ships; it is the apparatus that measures one.

The pieces, in the order a run touches them:

``schemas``
    Typed fixture documents and the validators that reject a malformed one with
    a message naming the file and the field.
``vocabularies``
    The four controlled vocabularies. Two are closed sets written down here;
    two are read from the running system, so a renamed capability or a retired
    root-cause category is a load error rather than a silent mismatch.
``loader``
    Discovery, inheritance, and the resolution of a directory into one value.
``backends``
    Recorded vendor responses served at the vendor boundary — below the
    capability, below the client, below the credential proxy — so everything a
    real integration does stays under test.
``determinism`` and ``offline``
    What makes two runs of the same scenario comparable, and what lets a run
    happen with no provider at all.
``runner`` and ``suite``
    One scenario through the canonical runtime and the real pipeline, and many
    of them with filtering and repeat attempts.
``artifacts``
    The per-attempt verdict record: enough to explain a failure without running
    it again.
"""

from __future__ import annotations

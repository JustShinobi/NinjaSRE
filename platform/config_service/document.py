"""What one node actually stores: its settings, and the policies it declares.

``ConfigNode.values`` is a JSONB payload and this is the envelope inside it. Two
members, and the separation is the reason FR-003 is satisfiable:

``settings``
    The node's own configuration values. This, and only this, is what the merge
    consumes. Nothing in it is ever interpreted — a key called ``_append`` is a
    field named ``_append``.

``field_policies``
    What this node declares about who may change what. Locks, required fields,
    approval gates, and value constraints. Outside the settings, so no
    configuration value can pass for a policy and no policy can be mistaken for
    a control key inside the merge.

A node stored before this envelope existed, or written by hand, reads as
settings with no policies rather than failing — ``NodeDocument.of_values``
accepts a bare mapping. That is the one piece of leniency in the package, and it
is here because refusing to resolve a hierarchy is refusing to investigate an
incident.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.config_service import FIELD_POLICIES_KEY, SETTINGS_KEY
from platform.config_service.field_policy import FieldPolicy, PolicySet
from platform.config_service.merge import Layer
from platform.persistence.ports import ConfigNode


@dataclass(frozen=True, slots=True)
class NodeDocument:
    """One node's stored configuration, unpacked."""

    settings: Mapping[str, Any] = field(default_factory=dict)
    policies: PolicySet = field(default_factory=PolicySet)

    @classmethod
    def of(
        cls,
        settings: Mapping[str, Any],
        *,
        locked: Sequence[str] = (),
        required: Sequence[str] = (),
        approval_gated: Sequence[str] = (),
        policies: Sequence[FieldPolicy] = (),
    ) -> NodeDocument:
        """Return a document from settings plus the policies stated the short way.

        The three keyword shortcuts cover what an operator writes most of the
        time. ``policies`` is for the rest — allowed values, ceilings, and any
        combination of flags on one path.
        """
        declared = list(policies)
        declared += [FieldPolicy(path=path, locked=True) for path in locked]
        declared += [FieldPolicy(path=path, required=True) for path in required]
        declared += [FieldPolicy(path=path, approval_gated=True) for path in approval_gated]
        return cls(settings=dict(settings), policies=PolicySet.of(declared))

    @classmethod
    def of_values(cls, values: Mapping[str, Any]) -> NodeDocument:
        """Return the document stored in a node's ``values`` payload."""
        if SETTINGS_KEY not in values and FIELD_POLICIES_KEY not in values:
            return cls(settings=dict(values))

        settings = values.get(SETTINGS_KEY) or {}
        declared = values.get(FIELD_POLICIES_KEY) or []
        return cls(
            settings=dict(settings) if isinstance(settings, Mapping) else {},
            policies=PolicySet.of_records(declared),
        )

    @classmethod
    def of_node(cls, node: ConfigNode) -> NodeDocument:
        """Return the document stored on ``node``."""
        return cls.of_values(node.values)

    def to_values(self) -> dict[str, Any]:
        """Return the payload to store in ``ConfigNode.values``."""
        return {
            SETTINGS_KEY: dict(self.settings),
            FIELD_POLICIES_KEY: self.policies.to_records(),
        }

    def as_layer(self, node_id: str) -> Layer:
        """Return this document as one layer of a merge."""
        return Layer(node_id=node_id, values=self.settings, locked=self.policies.locked_paths())

    def with_settings(self, settings: Mapping[str, Any]) -> NodeDocument:
        """Return this document with its settings replaced."""
        return NodeDocument(settings=dict(settings), policies=self.policies)

    def with_policies(self, policies: PolicySet) -> NodeDocument:
        """Return this document with its policies replaced."""
        return NodeDocument(settings=self.settings, policies=policies)


__all__ = ["NodeDocument"]

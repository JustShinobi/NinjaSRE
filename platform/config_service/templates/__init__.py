"""Reusable configuration bundles, applied to a node with a reviewable diff first.

``TemplateLibrary.golden()`` returns the seven NinjaSRE ships;
``TemplateLibrary.of_directory`` returns an operator's own. Both answer
``preview``, which is what a console renders before anybody presses apply.
"""

from __future__ import annotations

from platform.config_service.templates.engine import (
    ConfigTemplate,
    FieldChange,
    TemplateDiff,
    TemplateInvalid,
    TemplateLibrary,
    load,
    preview,
)

__all__ = [
    "ConfigTemplate",
    "FieldChange",
    "TemplateDiff",
    "TemplateInvalid",
    "TemplateLibrary",
    "load",
    "preview",
]

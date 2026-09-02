"""Applying a bundle of configuration, and showing what it would change first.

A template is a starting point, not a migration. An operator applying
``incident-triage-slack`` to a team that already has configuration needs to see
what it would overwrite *before* it does — which channel it is about to replace,
which model binding it is about to change — because a template that silently
overwrote a deliberate choice is a template nobody applies twice.

So ``preview`` is the primary operation and ``apply`` takes the diff it
produced. The diff is computed with the same ``deep_merge`` the hierarchy uses,
so what the preview shows and what the application does cannot disagree: they
are the same function.

Templates are documents rather than code. They ship as YAML beside this module
for the same reason guardrail rules do — an operator forks one, edits it, and
points a deployment at their own, and none of that should need a release.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import yaml

from config.constants.config_service import (
    GOLDEN_TEMPLATE_DIRECTORY,
    GOLDEN_TEMPLATES,
    TEMPLATE_FILE_SUFFIX,
)
from platform.config_service import paths
from platform.config_service.errors import UnknownTemplate
from platform.config_service.merge import deep_merge

#: Where the shipped templates live. Beside the code because they are part of
#: it: an operator who points at their own directory should still be able to
#: reach these by name.
GOLDEN_DIRECTORY: Final[Path] = Path(__file__).parent / GOLDEN_TEMPLATE_DIRECTORY

#: What a template document may declare.
TEMPLATE_FIELDS: Final[tuple[str, ...]] = ("name", "title", "summary", "use_case", "settings")


class TemplateInvalid(ValueError):
    """A template document is not one, and says which file and why."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"{source}: {reason}")
        self.source = source
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ConfigTemplate:
    """A reusable configuration bundle, applicable to a node."""

    name: str
    title: str = ""
    summary: str = ""
    use_case: str = ""
    settings: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of_document(cls, document: Any, source: str) -> ConfigTemplate:
        """Return the template ``document`` describes, or raise saying why not."""
        if not isinstance(document, Mapping):
            raise TemplateInvalid(source, "a template is a mapping of fields")
        unknown = sorted(set(document) - set(TEMPLATE_FIELDS))
        if unknown:
            raise TemplateInvalid(source, f"declares unknown fields: {', '.join(unknown)}")

        name = document.get("name")
        settings = document.get("settings")
        if not isinstance(name, str) or not name:
            raise TemplateInvalid(source, "a template needs a name to be applied by")
        if not isinstance(settings, Mapping):
            raise TemplateInvalid(source, "a template needs a settings section to apply")

        return cls(
            name=name,
            title=str(document.get("title", "")),
            summary=str(document.get("summary", "")),
            use_case=str(document.get("use_case", "")),
            settings=dict(settings),
        )


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One field a template would change, with what it is and what it becomes."""

    path: str
    before: Any
    after: Any

    @property
    def is_addition(self) -> bool:
        """Return whether this field has no value today."""
        return self.before is None

    def __str__(self) -> str:
        """Return the line a reviewer reads."""
        if self.is_addition:
            return f"+ {self.path} = {self.after!r}"
        return f"~ {self.path}: {self.before!r} -> {self.after!r}"


@dataclass(frozen=True, slots=True)
class TemplateDiff:
    """What applying a template would do, and the settings it would produce."""

    template: str
    changes: tuple[FieldChange, ...] = ()
    settings: Mapping[str, Any] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        """Return whether the template would change nothing."""
        return not self.changes

    def additions(self) -> tuple[FieldChange, ...]:
        """Return the fields this template would set that have no value today."""
        return tuple(change for change in self.changes if change.is_addition)

    def overwrites(self) -> tuple[FieldChange, ...]:
        """Return the fields this template would replace.

        The half of the diff a reviewer actually has to read: an addition is
        the template doing its job, and an overwrite is it disagreeing with a
        decision somebody already made.
        """
        return tuple(change for change in self.changes if not change.is_addition)

    def render(self) -> str:
        """Return the diff as reviewable text, one field per line."""
        if self.empty:
            return f"{self.template} would change nothing."
        return "\n".join(str(change) for change in self.changes)


@dataclass(frozen=True, slots=True)
class TemplateLibrary:
    """The templates a deployment can apply, loaded once from a directory."""

    templates: Mapping[str, ConfigTemplate] = field(default_factory=dict)

    @classmethod
    def golden(cls) -> TemplateLibrary:
        """Return the templates NinjaSRE ships.

        Loads by name rather than by walking the directory, and raises on one
        that is missing. A template that quietly stopped loading would be a
        template that quietly stopped being offered, and the console renders
        this list.

        Parsed once per process and shared. The files ship inside the
        package and cannot change while it runs, and every request that
        builds a configuration service asks for this library — reading and
        parsing them again each time was a fixed 28 ms on every such route.
        The library is frozen and its mapping read-only, which is what makes
        sharing one instance safe.
        """
        return _shipped_library()

    @classmethod
    def of_directory(cls, directory: Path) -> TemplateLibrary:
        """Return every template in ``directory``, keyed by name."""
        found: dict[str, ConfigTemplate] = {}
        for path in sorted(directory.glob(f"*{TEMPLATE_FILE_SUFFIX}")):
            template = load(path)
            found[template.name] = template
        return cls(templates=found)

    @classmethod
    def of(cls, templates: Sequence[ConfigTemplate]) -> TemplateLibrary:
        """Return a library over ``templates``."""
        return cls(templates={each.name: each for each in templates})

    def get(self, name: str) -> ConfigTemplate:
        """Return the template called ``name``, or raise listing what is installed."""
        found = self.templates.get(name)
        if found is None:
            raise UnknownTemplate(name, tuple(self.templates))
        return found

    def names(self) -> tuple[str, ...]:
        """Return every installed template's name, in name order."""
        return tuple(sorted(self.templates))

    def preview(self, name: str, settings: Mapping[str, Any]) -> TemplateDiff:
        """Return what applying ``name`` to ``settings`` would change (FR-019)."""
        return preview(self.get(name), settings)

    def apply(self, name: str, settings: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return ``settings`` with ``name`` applied."""
        return self.preview(name, settings).settings

    def __len__(self) -> int:
        """Return how many templates are installed."""
        return len(self.templates)


@cache
def _shipped_library() -> TemplateLibrary:
    """Read and parse the shipped templates, the one time this process does."""
    found: dict[str, ConfigTemplate] = {}
    for name in GOLDEN_TEMPLATES:
        path = GOLDEN_DIRECTORY / f"{name}{TEMPLATE_FILE_SUFFIX}"
        template = load(path)
        if template.name != name:
            raise TemplateInvalid(str(path), f"is named {template.name!r} but is filed as {name!r}")
        found[name] = template
    return TemplateLibrary(templates=MappingProxyType(found))


def forget_shipped_templates() -> None:
    """Drop the parsed shipped templates, so the next ``golden`` reads them again.

    For a test that wants to watch the read happen. Nothing in a running
    deployment calls this: the files it would re-read are the ones it shipped with.
    """
    _shipped_library.cache_clear()


def load(path: Path) -> ConfigTemplate:
    """Return the template stored at ``path``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as unreadable:
        raise TemplateInvalid(str(path), f"could not be read: {unreadable}") from unreadable
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as malformed:
        raise TemplateInvalid(str(path), f"is not valid YAML: {malformed}") from malformed
    return ConfigTemplate.of_document(document, str(path))


def preview(template: ConfigTemplate, settings: Mapping[str, Any]) -> TemplateDiff:
    """Return what applying ``template`` to ``settings`` would change.

    The merge is the same ``deep_merge`` the hierarchy uses, so a template
    applied to a node behaves exactly as a parent's settings would: sections
    merge, lists and scalars replace.
    """
    merged = deep_merge(settings, template.settings)
    before = dict(paths.leaves(settings))
    after = dict(paths.leaves(merged))

    changes = tuple(
        FieldChange(path=path, before=before.get(path), after=after.get(path))
        for path in sorted(before.keys() | after.keys())
        if before.get(path) != after.get(path)
    )
    return TemplateDiff(template=template.name, changes=changes, settings=merged)


__all__ = [
    "forget_shipped_templates",
    "GOLDEN_DIRECTORY",
    "TEMPLATE_FIELDS",
    "ConfigTemplate",
    "FieldChange",
    "TemplateDiff",
    "TemplateInvalid",
    "TemplateLibrary",
    "load",
    "preview",
]

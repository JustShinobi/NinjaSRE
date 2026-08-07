"""What an ablation experiment is, written down, so somebody else can re-run it.

FR-016 asks for declarative and reproducible configurations, and the two words
pull in the same direction: an arm that exists only as an argument somebody typed
is an experiment nobody can repeat, and a number from an experiment nobody can
repeat is an anecdote.

So an arm is a name, a list of mechanisms to remove, and a sentence saying why.
That is the whole of it. Everything else — which policy object each mechanism
maps onto, what "off" means for it — is derived from the switch table, which
means the file cannot go stale against the code and a rename is a load error
rather than a silent skip.

The refusals matter as much as the shape. A configuration naming a mechanism
nobody defined fails when the file is read, not three hours into a run; and no
arm may call itself the baseline, because two rows of that name is a report
nobody can read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants.evaluation import ABLATION_MECHANISMS, BASELINE_ARM
from tests.harness.ablation.switches import (
    MechanismSwitches,
    UnknownMechanism,
    check_mechanisms,
)


class AblationConfigError(ValueError):
    """An ablation configuration is not one, and this says which and why."""


@dataclass(frozen=True, slots=True)
class AblationConfig:
    """One arm of an ablation: a name, what it removes, and why it exists."""

    name: str
    disabled: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AblationConfigError("an ablation arm must have a name to appear in a table under")
        if self.name == BASELINE_ARM and self.disabled:
            raise AblationConfigError(
                f"an arm that disables {list(self.disabled)} may not be called {BASELINE_ARM!r}; "
                f"that name belongs to the run every other arm is measured against"
            )
        try:
            check_mechanisms(self.disabled)
        except UnknownMechanism as error:
            raise AblationConfigError(
                f"{self.name}: {error}; a configuration naming a mechanism nobody defined "
                f"would publish a table saying it measured something it never varied"
            ) from error
        if len(set(self.disabled)) != len(self.disabled):
            raise AblationConfigError(
                f"{self.name}: names {list(self.disabled)}, with a repeat; switching one "
                f"mechanism off twice is the same arm written ambiguously"
            )

    @property
    def is_baseline(self) -> bool:
        """Return whether this arm removes nothing."""
        return not self.disabled

    def switches(self, base: MechanismSwitches | None = None) -> MechanismSwitches:
        """Return the configuration this arm runs under.

        Derived from the arm alone, which is what "reproducible" has to mean:
        the file is the whole of the experiment, and nothing about the machine it
        ran on can change what it removed.
        """
        return (base if base is not None else MechanismSwitches()).without(*self.disabled)

    def to_document(self) -> dict[str, Any]:
        """Return this arm as the mapping a configuration file holds."""
        document: dict[str, Any] = {"name": self.name, "disabled": list(self.disabled)}
        if self.description:
            document["description"] = self.description
        return document

    @classmethod
    def of_document(cls, document: Any, *, source: str) -> AblationConfig:
        """Return the arm ``document`` describes, or raise naming ``source``.

        Raises:
            AblationConfigError: the document is malformed or names a mechanism
                nobody defined.
        """
        if not isinstance(document, Mapping):
            raise AblationConfigError(f"{source}: an ablation arm is a mapping of fields")
        name = document.get("name")
        if not isinstance(name, str) or not name.strip():
            raise AblationConfigError(f"{source}: an ablation arm must have a name")

        raw = document.get("disabled") or ()
        if isinstance(raw, str) or not isinstance(raw, Sequence):
            raise AblationConfigError(
                f"{source}: {name}: 'disabled' must be a list of mechanism names"
            )
        try:
            return cls(
                name=name.strip(),
                disabled=tuple(str(item).strip() for item in raw),
                description=str(document.get("description", "")),
            )
        except AblationConfigError as error:
            raise AblationConfigError(f"{source}: {error}") from error


def baseline_config() -> AblationConfig:
    """Return the arm every other arm is measured against."""
    return AblationConfig(
        name=BASELINE_ARM,
        description="every mechanism on: the run the contributions are subtracted from",
    )


def one_at_a_time() -> tuple[AblationConfig, ...]:
    """Return the baseline plus one arm per mechanism.

    The suite worth running by default. Removing mechanisms in combination
    measures interactions, which is a real question and a different one — and a
    default that ran the power set would cost two hundred and fifty-six suite
    runs to answer a question nobody asked.
    """
    from tests.harness.ablation.switches import mechanism

    return (
        baseline_config(),
        *(
            AblationConfig(
                name=f"no-{name.replace('_', '-')}",
                disabled=(name,),
                description=mechanism(name).summary,
            )
            for name in ABLATION_MECHANISMS
        ),
    )


def write_configs(configs: Sequence[AblationConfig], path: Path) -> Path:
    """Write ``configs`` to ``path`` as a configuration file, and return it."""
    import yaml

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"configurations": [config.to_document() for config in configs]}, sort_keys=False
        ),
        encoding="utf-8",
    )
    return path


def load_configs(path: Path) -> tuple[AblationConfig, ...]:
    """Return the arms declared in the configuration file at ``path``.

    Raises:
        AblationConfigError: the file is missing, malformed, or names a mechanism
            nobody defined — naming the file in every case, because the person
            reading the failure is the person editing it.
    """
    import yaml

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise AblationConfigError(f"{path}: could not be read: {error}") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise AblationConfigError(f"{path}: is not valid YAML: {error}") from error

    if not isinstance(document, Mapping):
        raise AblationConfigError(f"{path}: an ablation file is a mapping with 'configurations'")
    raw = document.get("configurations")
    if isinstance(raw, str) or not isinstance(raw, Sequence) or not raw:
        raise AblationConfigError(
            f"{path}: 'configurations' must be a non-empty list of ablation arms"
        )

    configs = tuple(AblationConfig.of_document(item, source=str(path)) for item in raw)
    names = [config.name for config in configs]
    if len(set(names)) != len(names):
        raise AblationConfigError(
            f"{path}: two arms share a name ({sorted(names)}); a report keyed on the name "
            f"would silently merge them"
        )
    return configs


__all__ = [
    "AblationConfig",
    "AblationConfigError",
    "baseline_config",
    "load_configs",
    "one_at_a_time",
    "write_configs",
]

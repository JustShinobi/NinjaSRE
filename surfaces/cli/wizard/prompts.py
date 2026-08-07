"""Asking a person for something, in a way a test can drive and a shell cannot leak.

Two rules, and the second is the reason this is a protocol rather than four
calls to ``typer.prompt``.

**A secret is never echoed and never remembered.** ``secret`` reads with the
echo off and hands the value straight to whoever is writing it to the vault.
Nothing here stores one, logs one, or puts one in a default, and there is no
method that takes a credential as an argument — which is the same absence that
makes ``Vault`` checkable.

**Every prompt is answerable by a script.** ``ScriptedPrompter`` replays a list,
so the whole onboarding flow is a unit test rather than something somebody has
to sit and type. A wizard nobody can test is a wizard that breaks on the ninth
provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import typer

from surfaces.cli.errors import CliError


class PromptAbandoned(CliError):
    """The person answering stopped, and nothing further should be asked.

    Distinct from a failure: an operator pressing Ctrl+D partway through
    onboarding has not broken anything, and telling them they have is how a
    guided flow becomes something people avoid.
    """


@runtime_checkable
class Prompter(Protocol):
    """Everything the wizard asks a person."""

    def ask(self, question: str, *, default: str = "", help_text: str = "") -> str:
        """Return a line of text, echoed as it is typed."""

    def secret(self, question: str, *, help_text: str = "") -> str:
        """Return a value read without echo, for something nobody may see."""

    def choose(self, question: str, options: Sequence[str], *, default: str = "") -> str:
        """Return one of ``options``."""

    def confirm(self, question: str, *, default: bool = False) -> bool:
        """Return a yes or a no."""

    def say(self, message: str) -> None:
        """Show something that is not a question."""


@dataclass(slots=True)
class TyperPrompter:
    """Asks through the terminal.

    ``hide_input`` on the secret path is the terminal half of keeping a
    credential off the disk: a value that was never drawn is a value that is not
    in a screen recording, a scrollback buffer, or the shoulder of the person
    beside you.
    """

    def ask(self, question: str, *, default: str = "", help_text: str = "") -> str:
        """Return a line of text, echoed as it is typed."""
        if help_text:
            typer.echo(f"  {help_text}")
        try:
            return str(typer.prompt(question, default=default, show_default=bool(default)))
        except (EOFError, typer.Abort) as stopped:
            raise PromptAbandoned("nothing more was entered") from stopped

    def secret(self, question: str, *, help_text: str = "") -> str:
        """Return a value read without echo, for something nobody may see."""
        if help_text:
            typer.echo(f"  {help_text}")
        try:
            return str(typer.prompt(question, hide_input=True, show_default=False))
        except (EOFError, typer.Abort) as stopped:
            raise PromptAbandoned("nothing more was entered") from stopped

    def choose(self, question: str, options: Sequence[str], *, default: str = "") -> str:
        """Return one of ``options``."""
        if not options:
            raise CliError(f"{question}: there is nothing to choose from")
        for index, option in enumerate(options, start=1):
            typer.echo(f"  {index:>2}. {option}")
        while True:
            answer = self.ask(question, default=default)
            if answer in options:
                return answer
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1]
            typer.echo(f"  {answer!r} is not one of these.")

    def confirm(self, question: str, *, default: bool = False) -> bool:
        """Return a yes or a no."""
        try:
            return bool(typer.confirm(question, default=default))
        except (EOFError, typer.Abort) as stopped:
            raise PromptAbandoned("nothing more was entered") from stopped

    def say(self, message: str) -> None:
        """Show something that is not a question."""
        typer.echo(message)


@dataclass(slots=True)
class ScriptedPrompter:
    """Replays prepared answers, for a test or an unattended run.

    ``said`` is kept so a test can assert what the operator was told, which is
    most of what a wizard is: the questions are the easy part, and the guidance
    around them is what decides whether somebody finishes.
    """

    answers: list[str] = field(default_factory=list)
    confirmations: list[bool] = field(default_factory=list)
    said: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    secrets_asked: list[str] = field(default_factory=list)
    #: Guidance shown alongside a prompt. Recorded because a test asserting
    #: that somebody was told where to find their API key is asserting the part
    #: of a wizard that decides whether they finish it.
    guidance_shown: list[str] = field(default_factory=list)

    def _next(self, question: str, default: str) -> str:
        """Return the next prepared answer, or the default when the script ran out."""
        self.asked.append(question)
        if not self.answers:
            if default:
                return default
            raise PromptAbandoned(f"the script has no answer for {question!r}")
        return self.answers.pop(0)

    def ask(self, question: str, *, default: str = "", help_text: str = "") -> str:
        """Return the next prepared answer."""
        if help_text:
            self.guidance_shown.append(help_text)
        return self._next(question, default)

    def secret(self, question: str, *, help_text: str = "") -> str:
        """Return the next prepared answer, recorded as having been asked in secret."""
        if help_text:
            self.guidance_shown.append(help_text)
        self.secrets_asked.append(question)
        return self._next(question, "")

    def choose(self, question: str, options: Sequence[str], *, default: str = "") -> str:
        """Return the next prepared answer, resolved against ``options``."""
        answer = self._next(question, default)
        if answer in options:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        raise CliError(f"{answer!r} is not one of {', '.join(options)}")

    def confirm(self, question: str, *, default: bool = False) -> bool:
        """Return the next prepared confirmation."""
        self.asked.append(question)
        return self.confirmations.pop(0) if self.confirmations else default

    def say(self, message: str) -> None:
        """Record what the operator was told."""
        self.said.append(message)


__all__ = [
    "PromptAbandoned",
    "Prompter",
    "ScriptedPrompter",
    "TyperPrompter",
]

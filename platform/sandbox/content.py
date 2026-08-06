"""Capability code and skill bodies, delivered so the sandbox cannot rewrite them.

Immutability here is a small requirement with a large consequence. If a sandbox can modify
the content it will execute next, then one compromised execution owns every
execution after it — and the compromise survives the release of the sandbox that
caused it, because the content outlives the instance.

So content is a value here, not a directory. A ``ContentBundle`` is an immutable
set of entries with a digest over the whole thing, ``materialise`` writes it out
without a write bit anywhere, and ``verify`` recomputes the digests before the
next execution. The two together mean tampering is detected on the way *in*
rather than discovered afterwards, which is the difference between a refusal and
a post-mortem.

The digest is what makes this checkable across profiles. ``process`` gets
read-only file modes, ``container`` gets a read-only bind mount, ``kubernetes``
gets a projected volume with ``readOnly: true`` — three mechanisms of quite
different strength, all of which fail the same digest check if they are wrong.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from platform.sandbox.errors import ContentTampered

#: Files land without any write bit; directories keep traverse and list.
_READ_ONLY_FILE_MODE = 0o444
_READ_ONLY_DIRECTORY_MODE = 0o555

#: Written before the modes are tightened, because a directory chmod-ed to 0o555
#: cannot receive the file that goes in it — the entries are materialised first
#: and the tree is sealed from the leaves up.
_WRITABLE_DIRECTORY_MODE = 0o755


@dataclass(frozen=True, slots=True)
class ContentEntry:
    """One file delivered into a sandbox, with the digest it must still have."""

    path: str
    data: bytes

    def __post_init__(self) -> None:
        pure = PurePosixPath(self.path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(
                f"{self.path!r} is not a relative path inside the content mount. An "
                f"absolute path or a '..' segment would place delivered content "
                f"somewhere the mount does not cover, which is where read-only stops "
                f"being true."
            )

    @property
    def digest(self) -> str:
        """Return the SHA-256 of this entry's bytes, hex-encoded."""
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentBundle:
    """Everything a sandbox will execute, addressed by one digest.

    Entries are held in path order so the bundle digest is a property of the
    content rather than of the order somebody happened to add files in. Two
    deployments delivering the same capabilities produce the same digest, which
    is what lets an audit line say *which* content ran.
    """

    entries: tuple[ContentEntry, ...] = ()

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.entries, key=lambda entry: entry.path))
        seen = [entry.path for entry in ordered]
        if len(set(seen)) != len(seen):
            raise ValueError("a content bundle cannot deliver two entries at the same path")
        object.__setattr__(self, "entries", ordered)

    @classmethod
    def empty(cls) -> ContentBundle:
        """Return the bundle that delivers nothing.

        The default for a sandbox that runs a command rather than capability
        code. Its digest is still stable, so "no content" is a value the audit
        trail records rather than an absence it cannot distinguish from a bug.
        """
        return cls()

    @classmethod
    def from_mapping(cls, files: Mapping[str, bytes | str]) -> ContentBundle:
        """Return a bundle of ``files``, keyed by relative path."""
        return cls(
            entries=tuple(
                ContentEntry(path=path, data=data.encode() if isinstance(data, str) else data)
                for path, data in files.items()
            )
        )

    @classmethod
    def from_directory(cls, root: Path, *, suffixes: Iterable[str] = ()) -> ContentBundle:
        """Return a bundle of every file under ``root``, optionally filtered by suffix.

        Reads eagerly. A bundle that lazily re-read its source would deliver
        whatever the source said at execution time, which is the property this
        module exists to remove.
        """
        wanted = frozenset(suffixes)
        entries: list[ContentEntry] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if wanted and path.suffix not in wanted:
                continue
            entries.append(
                ContentEntry(path=path.relative_to(root).as_posix(), data=path.read_bytes())
            )
        return cls(entries=tuple(entries))

    @property
    def digest(self) -> str:
        """Return the digest over every entry's path and content."""
        running = hashlib.sha256()
        for entry in self.entries:
            running.update(entry.path.encode())
            running.update(b"\0")
            running.update(entry.digest.encode())
            running.update(b"\0")
        return running.hexdigest()

    @property
    def total_bytes(self) -> int:
        """Return how much this bundle will occupy in the content mount."""
        return sum(len(entry.data) for entry in self.entries)

    def materialise(self, destination: Path) -> None:
        """Write every entry under ``destination`` with no write bit anywhere.

        The tree is sealed from the leaves up: a directory has to be writable
        while its files are being created, so modes are tightened afterwards
        rather than at creation.
        """
        destination.mkdir(parents=True, exist_ok=True)
        for entry in self.entries:
            target = destination / entry.path
            target.parent.mkdir(parents=True, exist_ok=True, mode=_WRITABLE_DIRECTORY_MODE)
            target.write_bytes(entry.data)
            os.chmod(target, _READ_ONLY_FILE_MODE)
        _seal_directories(destination)

    def verify(self, destination: Path) -> None:
        """Raise ``ContentTampered`` unless ``destination`` still holds this bundle.

        Called before an execution, not after. Detecting a modification on the
        way out would report the compromise once it had already run.
        """
        for entry in self.entries:
            target = destination / entry.path
            if not target.is_file():
                raise ContentTampered(entry.path)
            if hashlib.sha256(target.read_bytes()).hexdigest() != entry.digest:
                raise ContentTampered(entry.path)

    def release(self, destination: Path) -> None:
        """Restore write permission under ``destination`` so it can be removed.

        Cleanup needs it. A read-only tree cannot be deleted on Windows at all,
        and on POSIX only because the *parent* is writable — which is exactly
        the kind of platform difference a released sandbox should not depend on.
        """
        if not destination.exists():
            return
        for path in sorted(destination.rglob("*"), reverse=True):
            _make_writable(path)
        _make_writable(destination)


def _seal_directories(root: Path) -> None:
    """Remove the write bit from ``root`` and every directory beneath it."""
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            os.chmod(path, _READ_ONLY_DIRECTORY_MODE)
    os.chmod(root, _READ_ONLY_DIRECTORY_MODE)


def _make_writable(path: Path) -> None:
    """Add the owner write bit back to ``path``, whatever kind of node it is."""
    mode = path.stat().st_mode
    os.chmod(path, mode | stat.S_IWRITE | (stat.S_IEXEC if path.is_dir() else 0))


__all__ = [
    "ContentBundle",
    "ContentEntry",
]

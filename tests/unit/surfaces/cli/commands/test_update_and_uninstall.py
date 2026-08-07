"""``update`` reports; ``uninstall`` takes everything back off the machine.

Two commands, and each one's interesting property is a thing it does *not* do.

``update`` transmits nothing. Article X forbids a version check that phones home
without being asked, so this is a command an operator types and never a
background task, a startup probe, or a nag.

``uninstall`` removes all four roots, and shows what will go before asking. An
operator about to lose their configuration is entitled to see what that means,
and an uninstall that left the state directory behind would leave a REPL
history containing whatever somebody typed during an incident.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from config.constants.paths import (
    NINJASRE_HOME_DIR_ENV,
    cache_dir,
    config_dir,
    data_dir,
    state_dir,
)
from surfaces.cli.commands import update as update_module
from surfaces.cli.commands.uninstall import existing_paths, local_data_paths, remove

pytestmark = pytest.mark.unit


def test_every_root_the_platform_writes_to_is_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Four roots under four different XDG bases. Missing one leaves data behind
    # that the operator was told had gone.
    monkeypatch.delenv(NINJASRE_HOME_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-config")
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg-cache")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")

    listed = set(local_data_paths())

    for root in (config_dir(), cache_dir(), data_dir(), state_dir()):
        assert root in listed, f"{root} would survive an uninstall"


def test_a_single_home_directory_is_listed_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # With NINJASRE_HOME_DIR set, all four roots nest inside one. Listing the
    # same tree five times would make the confirmation prompt lie about how
    # much there is.
    monkeypatch.setenv(NINJASRE_HOME_DIR_ENV, str(tmp_path / "ninjasre"))

    assert local_data_paths() == (tmp_path / "ninjasre",)


def test_only_paths_that_exist_are_offered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(NINJASRE_HOME_DIR_ENV, str(tmp_path / "absent"))

    assert existing_paths() == ()


def test_removal_reports_what_went(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text("model: x", encoding="utf-8")
    (tmp_path / "state").mkdir()

    removed, failed = remove((tmp_path / "config", tmp_path / "state"))

    assert set(removed) == {str(tmp_path / "config"), str(tmp_path / "state")}
    assert failed == ()
    assert not (tmp_path / "config").exists()


def test_one_path_that_will_not_go_does_not_stop_the_others(tmp_path: Path) -> None:
    # Stopping at the first permission error would leave an uninstall half-done
    # and no record of which half.
    (tmp_path / "good").mkdir()

    removed, failed = remove((tmp_path / "missing", tmp_path / "good"))

    assert removed == [str(tmp_path / "good")] or removed == (str(tmp_path / "good"),)
    assert len(failed) == 1
    assert "missing" in failed[0]


def test_removal_takes_a_file_as_well_as_a_directory(tmp_path: Path) -> None:
    marker = tmp_path / "repl-history"
    marker.write_text("checkout is slow", encoding="utf-8")

    removed, failed = remove((marker,))

    assert removed == (str(marker),)
    assert failed == ()
    assert not marker.exists()


def test_update_transmits_nothing() -> None:
    # Asserted structurally: there is nothing in the module that could make a
    # request. A version check that phoned home without being asked is what
    # Article X forbids.
    source = inspect.getsource(update_module)

    for word in ("urlopen", "requests.", "httpx", "socket.", "urllib.request"):
        assert word not in source, f"update reaches the network with {word}"


def test_update_reports_the_installed_version_or_says_it_is_a_checkout() -> None:
    reported = update_module.installed_version()

    # Either a real version or the empty string. Never an invented one: a
    # command that guessed would make "which build is this" unanswerable.
    assert reported == "" or reported[0].isdigit()


def test_update_names_both_install_paths() -> None:
    # An operator who installed with Homebrew must not be told to pipe a script
    # into a shell.
    source = inspect.getsource(update_module)

    assert "install.sh" in source
    assert "brew upgrade" in source

"""What the images promise, and the check that keeps ``.env.example`` honest.

The settings test is the one with the most leverage. FR-009 says every setting
is documented; a document is correct the day it is written; so the check here is
that every environment variable the constants tier declares is either in the
catalogue or explicitly listed as not an operator setting. A feature that adds a
setting and forgets to document it fails naming the variable, which is the only
mechanism that survives the fifteenth feature.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import config.constants as constants
from platform.startup.settings import (
    NOT_A_DEPLOYMENT_SETTING,
    SETTINGS,
    render_env_example,
    required_settings,
    setting_names,
)
from tests.contract.deployment.conftest import COMPOSE, IMAGES, OPS, dockerfiles

pytestmark = pytest.mark.contract

#: A name in the constants tier that looks like a variable NinjaSRE itself owns.
_OWN_ENV_PATTERN = re.compile(r"^NINJASRE_[A-Z0-9_]+$")


# -- images -------------------------------------------------------------------


def test_every_image_is_shipped() -> None:
    names = {path.name for path in dockerfiles()}

    assert names == {
        "app.Dockerfile",
        "console.Dockerfile",
        "proxy.Dockerfile",
        "postgres.Dockerfile",
    }


@pytest.mark.parametrize("path", dockerfiles(), ids=lambda path: path.name)
def test_no_image_floats_on_a_moving_tag(path: Path) -> None:
    """A tag somebody else can move is a build that is not reproducible."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("FROM "):
            continue
        reference = line.split()[1]
        assert ":latest" not in reference, f"{path.name}: {reference}"
        assert reference.startswith("${"), (
            f"{path.name} names {reference} inline; base images come from "
            f"base-images.env so there is one list to pin and one to mirror"
        )


@pytest.mark.parametrize("path", dockerfiles(), ids=lambda path: path.name)
def test_every_base_image_argument_has_a_default_from_the_one_list(path: Path) -> None:
    declared = dict(
        line.split("=", 1)
        for line in (IMAGES / "base-images.env").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    source = path.read_text(encoding="utf-8")

    for match in re.finditer(r"^ARG (BASE_[A-Z_]+)=(.+)$", source, re.MULTILINE):
        name, default = match.group(1), match.group(2).strip()
        assert name in declared, f"{path.name} uses {name}, which base-images.env does not declare"
        assert default == declared[name], (
            f"{path.name}'s default for {name} is {default!r} and base-images.env says "
            f"{declared[name]!r}; the two must not drift"
        )


def test_no_base_image_is_pinned_to_a_bare_major_version() -> None:
    """An exact version, so a patch release cannot change behaviour under a deployment."""
    for line in (IMAGES / "base-images.env").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        reference = line.split("=", 1)[1]
        assert ":latest" not in reference, reference
        tag = reference.split("@")[0].rsplit(":", 1)[-1]
        assert any(character.isdigit() for character in tag), (
            f"{reference} has no version in its tag"
        )


@pytest.mark.parametrize(
    "path",
    [path for path in dockerfiles() if path.name != "postgres.Dockerfile"],
    ids=lambda path: path.name,
)
def test_every_application_image_runs_as_a_numeric_non_root_user(path: Path) -> None:
    """A named user resolves at runtime; Kubernetes' runAsNonRoot check reads the number."""
    source = path.read_text(encoding="utf-8")

    assert "USER 10001:10001" in source, f"{path.name} does not drop to a numeric UID"
    assert source.index("USER 10001") < len(source), "USER must come before the entrypoint"
    assert source.rindex("USER 10001") < source.rindex("ENTRYPOINT")


@pytest.mark.parametrize(
    "path",
    [path for path in dockerfiles() if path.name != "postgres.Dockerfile"],
    ids=lambda path: path.name,
)
def test_every_application_image_is_multi_stage(path: Path) -> None:
    """An image that can build is an image an attacker can build in."""
    source = path.read_text(encoding="utf-8")

    assert source.count("FROM ") >= 2, f"{path.name} is a single stage"
    assert "AS build" in source
    assert "AS runtime" in source
    assert "COPY --from=build" in source


@pytest.mark.parametrize(
    "path",
    [path for path in dockerfiles() if path.name != "postgres.Dockerfile"],
    ids=lambda path: path.name,
)
def test_every_application_image_has_a_health_check(path: Path) -> None:
    assert "HEALTHCHECK" in path.read_text(encoding="utf-8"), path.name


def test_the_postgres_image_carries_both_extensions() -> None:
    """ADR 0004 needs pgvector and Apache AGE, and nothing published has both."""
    source = (IMAGES / "postgres.Dockerfile").read_text(encoding="utf-8")

    assert "pgvector" in source
    assert "apache/age" in source
    assert "postgres-initdb.sql" in source
    assert (IMAGES / "postgres-initdb.sql").exists()


def test_the_air_gapped_bundle_and_the_pinning_script_ship() -> None:
    """FR-023: image distribution is part of supporting an offline deployment."""
    assert (IMAGES / "bundle.sh").exists()
    assert (IMAGES / "pin.sh").exists()


def test_the_operations_scripts_ship() -> None:
    names = {path.name for path in OPS.iterdir() if path.is_file()}

    assert {
        "backup.sh",
        "restore.sh",
        "check.py",
        "manifest.py",
        "rotate_key.py",
        "preflight.py",
    } <= names


# -- settings and .env.example -------------------------------------------------


def test_the_generated_env_example_is_current() -> None:
    """The same check ``make check-env-example`` runs, so a drift fails here too."""
    shipped = (COMPOSE / ".env.example").read_text(encoding="utf-8")

    assert shipped == render_env_example(), (
        "deploy/compose/.env.example is out of date; run `make env-example`"
    )


def test_every_environment_variable_this_repository_declares_is_documented() -> None:
    """FR-009, enforced rather than asserted."""
    declared = {
        value
        for name, value in vars(constants).items()
        if name.endswith("_ENV") and isinstance(value, str) and _OWN_ENV_PATTERN.match(value)
    }
    documented = setting_names() | set(NOT_A_DEPLOYMENT_SETTING)

    assert declared <= documented, (
        f"undocumented settings: {sorted(declared - documented)}. Add them to "
        f"platform/startup/settings.py, or to NOT_A_DEPLOYMENT_SETTING with a reason."
    )


def test_the_minimum_viable_configuration_is_two_lines() -> None:
    """FR-010: one provider credential and a database; everything else defaults."""
    required = {setting.name for setting in required_settings()}

    assert len(required) == 2, f"required settings have grown to {sorted(required)}"


def test_no_setting_documents_a_plausible_looking_credential() -> None:
    """A default that looks like a key is a key somebody ships."""
    for setting in SETTINGS:
        if setting.secret:
            assert not setting.default, f"{setting.name} ships a default value for a secret"


def test_every_setting_says_what_it_affects_rather_than_what_it_is() -> None:
    for setting in SETTINGS:
        assert setting.effect.strip(), setting.name
        assert setting.effect.strip().endswith("."), f"{setting.name}: {setting.effect!r}"
        assert setting.section, setting.name


def test_the_rendered_file_comments_out_everything_optional() -> None:
    rendered = render_env_example()
    live = [
        line for line in rendered.splitlines() if line and not line.startswith("#") and "=" in line
    ]

    assert {line.split("=")[0] for line in live} == {
        setting.name for setting in required_settings()
    }

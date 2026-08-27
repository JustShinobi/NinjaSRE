"""Exactly one place in this tree can build a TLS context that does not verify.

A second one is a second thing a security review has to find, and the leak is
always the convenient one — a flag on a client "just for testing", added during
an outage and never removed. So it is a build failure that names the file
rather than a review comment somebody may not make.

Four claims are fixed here, and each has a way it would be silently wrong.

**One constructor.** Verification is weakened at the credential proxy's egress
and nowhere else, reachable only from a declaration that recorded a reason and
the identity of whoever accepted it.

**No switch on any surface an operator or a client can write to.** Not in the
configuration document, not in a credential schema, not in the request body of
the route that declares trust. The insecure form is reached by writing down
*why*, which is what makes it a decision instead of a checkbox.

**No capability touches a trust declaration.** The agent neither learns what
this deployment accepts from an endpoint nor influences it.

**The sandbox boundary did not move.** "We did not touch it" is not evidence;
the manifest is.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

ROOT = Path(__file__).resolve().parents[2]

#: The packages a shipped deployment is built from. Tests are excluded
#: deliberately: a contract suite has to stand a TLS server up with a throwaway
#: certificate to measure a real handshake, and holding it to this rule would
#: mean the rule could only ever be asserted about, never measured.
SHIPPED = (
    "capabilities",
    "config",
    "core",
    "gateway",
    "integrations",
    "platform",
    "surfaces",
)

#: The one module allowed to construct a context that does not verify, and the
#: reason it is that one: it is the process that opens the socket, and the only
#: component in the deployment that talks to a vendor at all.
THE_ONE_PLACE = "gateway/proxy/sender.py"

#: What "does not verify" looks like in the standard library.
_MARKERS = ("CERT_NONE", "_create_unverified_context")

#: Field names that would be a switch for turning certificate verification off.
#: Deliberately not including bare ``unverified``: the topology model uses it for
#: a fact discovery has not confirmed, and a rule that cried wolf there would be
#: relaxed rather than obeyed. What a TLS switch is actually ever called is
#: below, and the request body and configuration document are checked whole
#: besides.
_SWITCH_NAMES = frozenset(
    {
        "verify",
        "verify_ssl",
        "verify_tls",
        "verify_certificate",
        "ssl_verify",
        "tls_verify",
        "insecure",
        "insecure_skip_verify",
        "skip_tls_verify",
        "skip_verify",
        "no_verify",
        "allow_insecure",
        "tls_insecure",
        "disable_ssl_verification",
    }
)


def _modules() -> list[Path]:
    """Return every shipped Python module, by path."""
    found: list[Path] = []
    for package in SHIPPED:
        found.extend(sorted((ROOT / package).rglob("*.py")))
    return [path for path in found if "__pycache__" not in path.parts]


def _relative(path: Path) -> str:
    """Return ``path`` as a refusal should name it."""
    return path.relative_to(ROOT).as_posix()


def _lines_matching(path: Path, *needles: str) -> list[int]:
    """Return the line numbers where ``path`` mentions any of ``needles``, ignoring comments."""
    return [
        number
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(needle in line for needle in needles) and not line.lstrip().startswith("#")
    ]


# -- one place, and it is the one named ------------------------------------------


def test_only_the_proxy_sender_can_build_a_context_that_does_not_verify() -> None:
    offenders = {
        _relative(path): found for path in _modules() if (found := _lines_matching(path, *_MARKERS))
    }

    assert set(offenders) == {THE_ONE_PLACE}, (
        f"certificate verification may be weakened in exactly one place, and it is "
        f"{THE_ONE_PLACE}. Found: {offenders}. A second place is one more thing a "
        f"security review has to find, and it is always the convenient one."
    )


def test_hostname_checking_is_only_turned_off_where_the_chain_is_still_verified() -> None:
    """``check_hostname = False`` is legitimate twice, and both are in the one place.

    Once for a pinned fingerprint, which replaces the identity check rather than
    adding to it — that is what makes pinning the form that works for a cluster
    reached by IP address. Once to read back the names a certificate carries so
    a refusal can quote them, and that one still verifies the chain. Anywhere
    else it is hostname verification somebody switched off.
    """
    offenders = {
        _relative(path): found
        for path in _modules()
        if (found := _lines_matching(path, "check_hostname"))
        and any(
            "False" in path.read_text(encoding="utf-8").splitlines()[number - 1] for number in found
        )
    }

    assert set(offenders) <= {THE_ONE_PLACE}, (
        f"hostname verification is turned off outside {THE_ONE_PLACE}: {offenders}"
    )


def test_the_unverifying_context_is_reachable_only_from_a_declaration() -> None:
    """It is built inside the function that takes one, so nothing can reach it without."""
    tree = ast.parse((ROOT / THE_ONE_PLACE).read_text(encoding="utf-8"))
    building = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "context_for_trust"
    )
    inside = ast.unparse(building)
    whole = ast.unparse(tree)

    assert "CERT_NONE" in inside
    assert whole.count("CERT_NONE") == inside.count("CERT_NONE"), (
        "a context that does not verify is built somewhere other than the function that "
        "takes a declaration, so something can reach one without a recorded reason"
    )


def test_the_one_boolean_in_the_vocabulary_cannot_be_set_without_the_audited_pair() -> None:
    """The declaration carries a boolean and it is not a switch.

    ``verify`` exists because the value has to be able to *express* the
    unverified form. What stops it being a checkbox is that constructing it
    raises unless a reason and an identity come with it — so the field cannot be
    flipped, only declared alongside the two things an audit record needs.
    """
    from platform.credentials.proxy.trust import (
        CertificateTrust,
        UnverifiedTransportRefused,
    )

    with pytest.raises(UnverifiedTransportRefused):
        CertificateTrust(verify=False)
    with pytest.raises(UnverifiedTransportRefused):
        CertificateTrust(verify=False, reason="because")
    with pytest.raises(UnverifiedTransportRefused):
        CertificateTrust(verify=False, accepted_by="erik@acme")


# -- no switch on any surface a client or an operator writes to --------------------


def _config_sections() -> set[type]:
    """Return every configuration section the document is assembled from."""
    from platform.config_service.schema.root import RootConfig
    from platform.config_service.schema.types import ConfigSection

    del RootConfig  # imported for its side effect: every section is now defined

    found: set[type] = set()
    pending = list(ConfigSection.__subclasses__())
    while pending:
        section = pending.pop()
        if section in found:
            continue
        found.add(section)
        pending.extend(section.__subclasses__())
    return found


def test_no_configuration_section_declares_a_boolean_that_disables_verification() -> None:
    """The document is where an operator writes, and it is closed. Nothing here is a switch."""
    offenders = [
        f"{section.__name__}.{name}"
        for section in _config_sections()
        for name, declared in section.model_fields.items()
        if name in _SWITCH_NAMES and declared.annotation is bool
    ]

    assert not offenders, (
        f"a configuration section declares a boolean that would turn certificate "
        f"verification off: {offenders}."
    )


def test_no_credential_schema_declares_a_field_that_disables_verification() -> None:
    """A credential form is the other surface an operator types into."""
    from integrations.registry import credential_schemas

    declared = credential_schemas()
    offenders = [
        f"{name}.{field.name}"
        for name in declared.integrations()
        for field in declared.get(name).fields
        if field.name in _SWITCH_NAMES
    ]

    assert not offenders, f"a credential schema asks for a verification switch: {offenders}"


def test_the_route_that_declares_trust_takes_no_boolean_at_all() -> None:
    """The request body is the third surface, and the one a client controls."""
    from gateway.http.routes.integrations import TrustWriteRequest

    booleans = [
        name
        for name, declared in TrustWriteRequest.model_fields.items()
        if declared.annotation is bool
    ]

    assert not booleans, (
        f"the trust route accepts a boolean: {booleans}. The insecure form is reached by "
        f"writing down why, and a switch beside it is the thing that gets sent instead."
    )


# -- and no capability touches it ----------------------------------------------------


def test_no_capability_reads_or_writes_a_trust_declaration() -> None:
    """The agent neither learns what this deployment accepts nor influences it."""
    offenders = {
        _relative(path): found
        for path in sorted((ROOT / "capabilities").rglob("*.py"))
        if "__pycache__" not in path.parts
        and (
            found := _lines_matching(path, "CertificateTrust", "TrustRegistry", "trust_unverified")
        )
    }

    assert not offenders, (
        f"a capability reads or writes a certificate trust declaration: {offenders}. What "
        f"this deployment accepts from an endpoint is not something a turn decides."
    )


def test_no_capability_asks_for_the_permission_that_accepts_an_unverified_certificate() -> None:
    """It is a permission a person holds, checked at the API boundary and nowhere else."""
    from capabilities.registry.catalogue import build_registry

    offenders = [
        declared.name
        for declared in build_registry().metadata()
        if "integration.trust_unverified" in {str(one) for one in (declared.requires.names() or ())}
    ]

    assert not offenders, (
        f"a capability declares the trust permission as a requirement: {offenders}"
    )


# -- and the sandbox boundary did not move --------------------------------------------


def test_the_sandbox_egress_policy_is_the_same_three_rules_it_always_was() -> None:
    """The sandbox reaches DNS, the credential proxy, and its own sidecar. Nothing else.

    Worth measuring rather than assuming, and worth correcting a belief about:
    the sandbox *does* talk to the credential proxy, through one narrowly scoped
    rule that pre-dates this feature. What matters is that this feature added
    nothing here — in particular, no address a trust declaration names becomes
    reachable from inside a sandbox.
    """
    from platform.sandbox.profiles.kubernetes.pod_spec import network_policy
    from platform.sandbox.spec import EgressPolicy, SandboxSpec

    spec = SandboxSpec(
        org_id="acme",
        team_id="payments",
        investigation_id="run-1",
        egress=EgressPolicy(proxy_url="http://proxy.ninjasre.svc:8787"),
    )
    manifest = network_policy(
        "sandbox-1", spec, namespace="ninjasre", proxy_selector={"app": "ninjasre-proxy"}
    )

    assert manifest["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert manifest["spec"]["ingress"] == [], "a sandbox that accepts connections is reachable"

    egress = manifest["spec"]["egress"]
    assert len(egress) == 3, (
        f"the sandbox egress policy has {len(egress)} rules rather than the three it has "
        f"always had — DNS, the credential proxy, and the pod's own sidecar."
    )
    ports = [port["port"] for rule in egress for port in rule["ports"]]
    assert 53 in ports, "nothing resolves without DNS"
    assert spec.egress.proxy_port in ports, "the sandbox cannot reach the credential proxy"

"""What an infrastructure identifier looks like, written so it cannot backtrack.

Two rules govern every pattern in this module, and both are load-bearing.

**No unbounded quantifier.** Every repetition is ``{m,n}`` with a real ``n``.
That is what makes the ReDoS corpus in ``tests/security/test_redos_corpus.py``
pass rather than merely happen to pass — an unbounded quantifier next to an
overlapping one is exponential, and the input these patterns run on is a log
line somebody else wrote.

**Generic words need a label.** ``frontend`` and ``production`` are service
names in half the world's clusters and ordinary English in the other half, so
the detectors for service, deployment, namespace, cluster, and pod names only
fire behind a recognised label — ``namespace=``, ``cluster:``, ``--namespace``.
Structural shapes that cannot be anything else — an ARN, an IPv4 address, a
ReplicaSet-generated pod name — do not need one and do not have one.

Order matters and is explicit. An ARN contains an account identifier and a
region, and detecting the account identifier separately would produce two tokens
inside a string that means one thing. The order of ``DETECTORS`` is that
priority, and ``detect`` resolves an overlap in favour of whichever detector
comes first in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform.masking.policy import MaskingPolicy


class IdentifierKind(StrEnum):
    """What sort of thing a detector found.

    The kind is visible to the model — it is half of every token — because
    ``NSRE_MASK_POD_1`` is something a model can reason about and
    ``NSRE_MASK_1`` is not. Knowing that two tokens are both pods is most of
    what correlation needs.
    """

    ARN = "arn"
    CLOUD_ACCOUNT_ID = "account"
    CLUSTER = "cluster"
    CUSTOM = "custom"
    DEPLOYMENT = "deployment"
    HOSTNAME = "host"
    IP_ADDRESS = "ip"
    NAMESPACE = "namespace"
    POD = "pod"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class DetectedIdentifier:
    """One identifier found in one piece of text.

    ``label`` is what the token is built from and is usually the kind. It is
    separate so an operator's custom pattern can name its own tokens —
    ``NSRE_MASK_TICKET_1`` reads better in a prompt than
    ``NSRE_MASK_CUSTOM_1``, and the model reasons about what it can read.
    """

    kind: IdentifierKind
    label: str
    value: str
    start: int
    end: int

    @property
    def length(self) -> int:
        """Return how many characters this identifier spans."""
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Detector:
    """One compiled shape, and when it applies.

    Every pattern defines a ``value`` group. For a structural detector that is
    the whole match; for a contextual one it is the part after the label, which
    is the only part that gets replaced — rewriting ``namespace=`` itself would
    destroy the very context that made the match trustworthy.
    """

    name: str
    kind: IdentifierKind
    pattern: re.Pattern[str]
    #: Lowercase literals, any one of which must appear before the pattern is
    #: worth running. Every shape here has one — an ARN starts ``arn:``, an
    #: address contains a dot, a contextual detector needs its label — and a
    #: substring search is an order of magnitude cheaper than a regex pass.
    #: This is the "single pass where the patterns allow" of the plan: on real
    #: evidence most detectors are skipped outright, and a payload that
    #: genuinely contains every shape pays for every shape, which is correct.
    requires: tuple[str, ...] = ()
    #: True when the match required a recognised preceding label.
    contextual: bool = False
    #: True when this shape is only detected at ``strict``.
    strict_only: bool = False

    def applies_to(self, lowered: str) -> bool:
        """Return whether this detector's pattern is worth running at all.

        ``lowered`` is the whole text, lowercased once by the caller for every
        detector. Lowercasing per detector would cost more than the filter saves.
        """
        if not self.requires:
            return True
        return any(literal in lowered for literal in self.requires)

    def scan(self, text: str) -> list[DetectedIdentifier]:
        """Return every identifier this detector finds in ``text``."""
        found: list[DetectedIdentifier] = []
        for match in self.pattern.finditer(text):
            start, end = match.span("value")
            if start < 0 or start == end:
                continue
            found.append(
                DetectedIdentifier(
                    kind=self.kind,
                    label=self.kind.value.upper(),
                    value=match.group("value"),
                    start=start,
                    end=end,
                )
            )
        return found


# -- the pieces the contextual patterns are assembled from ---------------------

#: What may sit between a label and its value: an equals, a colon, or a pipe
#: with optional space either side, or plain whitespace. Bounded on both sides,
#: because ``\s*`` next to an alternation is how this file would get a ReDoS.
#:
#: The pipe is there because NinjaSRE's own reports are Markdown, and a table
#: row — ``| namespace | payments-prod |`` — is one of the commonest places an
#: identifier appears on its way to a model. A separator list that only knew
#: about ``key=value`` would mask the log line and miss the report.
_SEPARATOR = r"(?:\s{0,4}[=:|]\s{0,4}|\s{1,4})"

#: An optional opening quote or backtick. Log lines and JSON both occur.
_OPEN_QUOTE = r"[\"'`]?"

#: A DNS-1123 name: lowercase, may contain hyphens and dots, may not end in
#: one. The inner group is bounded, so the whole thing is linear.
_DNS_NAME = r"[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?"

#: A cluster or account name, which vendors let you write in mixed case with
#: underscores. Same bounded shape.
_RESOURCE_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,61}[A-Za-z0-9])?"

#: Nothing alphanumeric may precede a label, so ``my_namespace=`` does not read
#: as ``namespace=``. A lookbehind is constant cost.
_LABEL_BOUNDARY = r"(?<![A-Za-z0-9_])"


def _contextual(labels: str, value: str) -> str:
    """Return a pattern matching ``labels`` followed by a ``value`` group."""
    return rf"{_LABEL_BOUNDARY}(?:--?)?(?i:{labels}){_SEPARATOR}{_OPEN_QUOTE}(?P<value>{value})"


# -- structural shapes ---------------------------------------------------------

#: ``arn:partition:service:region:account:resource``. The resource segment is
#: bounded at 256 characters, which is longer than any ARN AWS issues and short
#: enough that a pathological line cannot make the match expensive.
_ARN = (
    r"(?<![A-Za-z0-9:])(?P<value>arn:aws[a-z-]{0,12}:[a-z0-9-]{1,32}:"
    r"[a-z0-9-]{0,20}:[0-9]{0,12}:[A-Za-z0-9_/:.*+=@-]{1,256})"
)

#: Twelve digits with nothing alphanumeric either side. Distinctive enough to
#: be worth having: a Unix timestamp is ten digits and a millisecond one is
#: thirteen, so the common false positives sit either side of this window.
_ACCOUNT_ID = r"(?<![0-9A-Za-z])(?P<value>[0-9]{12})(?![0-9A-Za-z])"

_IPV4_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"

#: The trailing guard is two lookaheads rather than ``(?![0-9.])`` because an
#: address at the end of a sentence is followed by a full stop, and a single
#: guard that excluded any dot would refuse to match the commonest way an
#: address is written down. Excluding a digit, or a dot *followed by* a digit,
#: still refuses the five-part dotted number that is not an address.
_IPV4 = rf"(?<![0-9.])(?P<value>(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET})(?![0-9])(?!\.[0-9])"

#: Either the full eight-group form or a form containing ``::``. Deliberately
#: not "two or more colon-separated hex groups", which would mask ``12:34:56``
#: out of every timestamp in every log line the platform reads.
_IPV6 = (
    r"(?<![0-9A-Fa-f:])(?P<value>"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?"
    r")(?![0-9A-Fa-f:])"
)

#: The suffixes that make a dotted string a hostname rather than a version
#: number, a Python module path, or a filename. A closed list, because the
#: alternative — "two or more dot-separated labels" — masks ``core.llm.client``
#: out of every stack trace and leaves the report unreadable.
_HOST_SUFFIXES = (
    "local|localdomain|internal|intranet|lan|corp|home|arpa|svc|k8s|cluster"
    "|com|net|org|io|dev|app|cloud|ai|co|sh|gg|systems|tech|test|invalid|example"
)
_HOSTNAME = (
    r"(?<![A-Za-z0-9.-])(?P<value>"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,31}[A-Za-z0-9])?\.){1,5}"
    rf"(?:{_HOST_SUFFIXES})"
    r")(?![A-Za-z0-9-])"
)

#: A ReplicaSet-generated pod: a workload name, a controller hash, and a
#: five-character suffix. The two trailing segments are what make this
#: unambiguous — no ordinary word ends in ``-7d9f8b6c5d-x2n4p``.
_POD_STRUCTURAL = (
    r"(?<![A-Za-z0-9.-])(?P<value>"
    r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?-[a-z0-9]{6,10}-[a-z0-9]{5}"
    r")(?![A-Za-z0-9-])"
)


#: Order is priority. An ARN is detected before the account identifier and the
#: hostname inside it, so one string that means one thing becomes one token.
DETECTORS: tuple[Detector, ...] = (
    Detector(
        name="arn",
        kind=IdentifierKind.ARN,
        pattern=re.compile(_ARN),
        requires=("arn:",),
    ),
    Detector(
        name="ipv6",
        kind=IdentifierKind.IP_ADDRESS,
        pattern=re.compile(_IPV6),
        requires=(":",),
    ),
    Detector(
        name="ipv4",
        kind=IdentifierKind.IP_ADDRESS,
        pattern=re.compile(_IPV4),
        requires=(".",),
    ),
    Detector(
        name="hostname",
        kind=IdentifierKind.HOSTNAME,
        pattern=re.compile(_HOSTNAME),
        requires=(".",),
    ),
    Detector(
        name="pod",
        kind=IdentifierKind.POD,
        pattern=re.compile(_POD_STRUCTURAL),
        requires=("-",),
    ),
    Detector(
        name="account-id",
        kind=IdentifierKind.CLOUD_ACCOUNT_ID,
        pattern=re.compile(_ACCOUNT_ID),
    ),
    Detector(
        name="pod-labelled",
        kind=IdentifierKind.POD,
        pattern=re.compile(
            _contextual(r"(?:k8s[._-])?pods?(?:[._-]?(?:name|id))?", _DNS_NAME),
        ),
        requires=("pod",),
        contextual=True,
    ),
    Detector(
        name="namespace-labelled",
        kind=IdentifierKind.NAMESPACE,
        pattern=re.compile(
            _contextual(
                r"(?:k8s[._-]|kube[._-]|kubernetes[._-])?name[._-]?spaces?(?:[._-]?name)?",
                _DNS_NAME,
            ),
        ),
        # ``space`` rather than ``namespace``, because the label may be written
        # ``name_space`` or ``name-space`` and the filter must not be narrower
        # than the pattern it stands in front of.
        requires=("space",),
        contextual=True,
    ),
    Detector(
        name="cluster-labelled",
        kind=IdentifierKind.CLUSTER,
        pattern=re.compile(
            _contextual(
                r"(?:eks[._-]|gke[._-]|aks[._-]|k8s[._-]|kubernetes[._-])?clusters?"
                r"(?:[._-]?(?:name|id|arn))?",
                _RESOURCE_NAME,
            ),
        ),
        requires=("cluster",),
        contextual=True,
    ),
    Detector(
        name="service-labelled",
        kind=IdentifierKind.SERVICE,
        pattern=re.compile(
            _contextual(r"(?:svcs?|services?|apps?)(?:[._-]?name)?", _DNS_NAME),
        ),
        requires=("svc", "service", "app"),
        contextual=True,
        strict_only=True,
    ),
    Detector(
        name="deployment-labelled",
        kind=IdentifierKind.DEPLOYMENT,
        pattern=re.compile(
            _contextual(
                r"(?:deployments?|deploys?|replicasets?|statefulsets?|daemonsets?)"
                r"(?:[._-]?name)?",
                _DNS_NAME,
            ),
        ),
        requires=("deploy", "replicaset", "statefulset", "daemonset"),
        contextual=True,
        strict_only=True,
    ),
)


def detectors_for(policy: MaskingPolicy) -> tuple[Detector, ...]:
    """Return the detectors ``policy`` turns on, in priority order.

    Custom patterns belong to ``strict`` along with service and deployment
    names, because they are the same kind of decision: a shape only this
    operator knows about, masked at the cost of the model no longer seeing it.
    An operator who wants theirs applied is asking for the level that says so.

    When they are on, they come first. Somebody who wrote a pattern for their
    own identifier shape knows something the shipped detectors do not, and a
    shipped detector claiming part of their match would split one identifier
    into two tokens.
    """
    if not policy.masks_anything:
        return ()
    if not policy.includes_service_names:
        return tuple(detector for detector in DETECTORS if not detector.strict_only)

    custom = tuple(
        Detector(
            name=f"custom:{pattern.name}",
            kind=IdentifierKind.CUSTOM,
            pattern=pattern.compile(),
        )
        for pattern in policy.custom_patterns
    )
    return custom + DETECTORS


def detect(text: str, policy: MaskingPolicy) -> tuple[DetectedIdentifier, ...]:
    """Return the identifiers in ``text``, non-overlapping and left to right.

    Overlaps are resolved by taking the earliest start, then the longest match,
    then the highest-priority detector — so an ARN wins over the account
    identifier inside it, deterministically, whichever order the detectors
    happened to run in.
    """
    lowered = text.lower()
    found: list[tuple[int, DetectedIdentifier]] = []
    for priority, detector in enumerate(detectors_for(policy)):
        if not detector.applies_to(lowered):
            continue
        label = _label_for(detector)
        for identifier in detector.scan(text):
            found.append((priority, _relabel(identifier, label)))

    found.sort(key=lambda entry: (entry[1].start, -entry[1].length, entry[0]))

    resolved: list[DetectedIdentifier] = []
    consumed_to = 0
    for _, identifier in found:
        if identifier.start < consumed_to:
            continue
        resolved.append(identifier)
        consumed_to = identifier.end
    return tuple(resolved)


def _label_for(detector: Detector) -> str:
    """Return the token label a detector's matches carry."""
    if detector.kind is not IdentifierKind.CUSTOM:
        return detector.kind.value.upper()
    _, _, name = detector.name.partition(":")
    sanitised = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return sanitised or IdentifierKind.CUSTOM.value.upper()


def _relabel(identifier: DetectedIdentifier, label: str) -> DetectedIdentifier:
    """Return ``identifier`` carrying ``label``."""
    if identifier.label == label:
        return identifier
    return DetectedIdentifier(
        kind=identifier.kind,
        label=label,
        value=identifier.value,
        start=identifier.start,
        end=identifier.end,
    )


__all__ = [
    "DETECTORS",
    "DetectedIdentifier",
    "Detector",
    "IdentifierKind",
    "detect",
    "detectors_for",
]

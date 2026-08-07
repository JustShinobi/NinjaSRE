"""A vendor that lives in several places, described once instead of coded twice.

Regional vendors are the quiet cost of a large catalogue. Datadog serves six
hosts, AWS serves one per region per service, and a European deployment that
sends its logs query to the American host gets a 403 that reads like a
permissions problem and is not. The failure is cheap to cause and expensive to
diagnose, which is the profile of everything worth putting in a framework.

FR-007 says regions are configuration rather than code, and the practical test of
that is whether adding a region is a data change. Here it is: a ``RegionMap`` is
a tuple of names and the host each resolves to, and ``from_template`` builds the
whole tuple from one pattern for the vendors — AWS and its relatives — whose
hosts are mechanical.

**The map is also the allow-list.** ``hosts()`` is what an ``InjectionRule``
takes, so the set of hosts the proxy will permit and the set the client can
address are one tuple rather than two that drift. Two lists is how an
integration ends up permitted to reach a region it can no longer name, which is
a wider egress surface than anybody chose.

**No wildcards, deliberately.** ``*.vendor.com`` is one delegated zone away from
permitting a host nobody approved, and the vendors that genuinely have unbounded
host sets — a self-hosted appliance, a Kubernetes API server — are the ones the
operator declares, which is a different mechanism and lives with them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: The placeholder ``from_template`` substitutes. Chosen to be obvious in a
#: pattern read out of a vendor's documentation.
REGION_PLACEHOLDER = "{region}"


class UnknownRegion(LookupError):
    """A region nobody declared, named alongside the ones that exist.

    Never a bare ``KeyError``. An operator who typed ``eu-west`` for
    ``eu-west-1`` needs to see the list, and a stack trace ending in a
    dictionary lookup does not show them one.
    """

    def __init__(self, integration: str, region: str, known: tuple[str, ...]) -> None:
        self.integration = integration
        self.region = region
        self.known = known
        super().__init__(
            f"{integration} has no region named {region!r}. Declared regions: "
            f"{', '.join(known) if known else 'none'}"
        )


@dataclass(frozen=True, slots=True)
class Region:
    """One place a vendor serves its API from."""

    name: str
    host: str
    display_name: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a region must have a name an operator can select it by")
        if not self.host.strip() or "/" in self.host:
            raise ValueError(
                f"{self.name}: a region's host is a host name, not a URL — the scheme and "
                f"path belong to the request, and a URL here would enter the egress "
                f"allow-list as one"
            )

    @property
    def label(self) -> str:
        """Return what a console shows for this region."""
        return self.display_name or self.name


@dataclass(frozen=True, slots=True)
class RegionMap:
    """Every region one vendor serves, and the host each resolves to."""

    integration: str
    regions: tuple[Region, ...]
    default: str
    scheme: str = "https"

    def __post_init__(self) -> None:
        if not self.regions:
            raise ValueError(f"{self.integration}: a region map with no regions permits nothing")
        names = [region.name for region in self.regions]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"{self.integration}: declares region {duplicates} more than once")
        if self.default not in names:
            raise ValueError(
                f"{self.integration}: the default region {self.default!r} is not one of "
                f"{', '.join(sorted(names))}"
            )

    @classmethod
    def from_template(
        cls,
        integration: str,
        *,
        template: str,
        names: Iterable[str],
        default: str,
        labels: Mapping[str, str] | None = None,
    ) -> RegionMap:
        """Return a map whose hosts all follow one pattern.

        For the vendors whose host names are mechanical —
        ``logs.{region}.amazonaws.com`` — this is what keeps a region list a
        data change. ``labels`` names the ones a console should not show as a
        slug.
        """
        if REGION_PLACEHOLDER not in template:
            raise ValueError(
                f"{integration}: the host template {template!r} has no {REGION_PLACEHOLDER}, so "
                f"every region would resolve to the same host"
            )
        shown = labels or {}
        return cls(
            integration=integration,
            regions=tuple(
                Region(
                    name=name,
                    host=template.replace(REGION_PLACEHOLDER, name),
                    display_name=shown.get(name, ""),
                )
                for name in names
            ),
            default=default,
        )

    @classmethod
    def single(cls, integration: str, *, host: str, name: str = "global") -> RegionMap:
        """Return a map for a vendor that serves one host everywhere.

        Worth having rather than making single-region vendors special: the
        catalogue then reports a region for every integration, and a console
        rendering "global" is doing less work than one branching on absence.
        """
        return cls(integration=integration, regions=(Region(name=name, host=host),), default=name)

    def names(self) -> tuple[str, ...]:
        """Return every declared region name, in declaration order."""
        return tuple(region.name for region in self.regions)

    def hosts(self) -> tuple[str, ...]:
        """Return every host this vendor may be reached at — the egress allow-list."""
        return tuple(dict.fromkeys(region.host for region in self.regions))

    def get(self, name: str = "") -> Region:
        """Return the named region, or the default when ``name`` is blank."""
        wanted = name.strip() or self.default
        for region in self.regions:
            if region.name == wanted:
                return region
        raise UnknownRegion(self.integration, wanted, self.names())

    def host_for(self, name: str = "") -> str:
        """Return the host serving ``name``, or the default region's."""
        return self.get(name).host

    def base_url(self, name: str = "", *, path: str = "") -> str:
        """Return the base URL a client built for ``name`` should address."""
        url = f"{self.scheme}://{self.host_for(name)}"
        return f"{url}/{path.lstrip('/')}" if path else url

    def to_records(self) -> tuple[dict[str, str], ...]:
        """Return the JSON-serialisable form the catalogue and console render."""
        return tuple(
            {"name": region.name, "host": region.host, "label": region.label}
            for region in self.regions
        )


__all__ = [
    "REGION_PLACEHOLDER",
    "Region",
    "RegionMap",
    "UnknownRegion",
]

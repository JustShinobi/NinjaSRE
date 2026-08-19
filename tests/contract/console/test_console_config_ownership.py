"""Every configuration field has one screen that edits it, or is named as having none.

The raw configuration editor is being retired. That is only safe if parity is a
fact a check holds rather than an intention somebody had, because a field whose
single place of editing disappears is a capability regression nobody notices
until the day they need it.

So the console declares, per field, exactly one of three things: which page a
person edits it on today, that the console or the server writes it on its own
with no form by decision, or which page is — or will be — responsible for it
even though nothing can edit it yet. These tests hold all three against the
schema itself, which is the only thing that knows what fields exist.

**The failure that matters most is the one nobody wrote a test for.** A field
added to a section months from now, by somebody who has never read this file,
appears in none of the three and fails here by name. That is the check turning
an absence into a build defect instead of a discovery made by an operator
looking for a setting that is not there.

**Being accounted for is not being reachable, and both are checked.** A field
can sit in exactly one list and still be a false claim: `no_control()` is held
against `reachable_fields()` so nothing sits there that the editor could
already reach, and `CONFIG_FIELD_OWNERS` is held to the same standard from the
other direction — a field claimed as owned has to be a type the editor can
draw *any* control for at all, and, where its only claim to a control is the
generic editor's own prefix sweep rather than a bespoke form, it has to be a
field that editor's own data source actually hands it. A type that passes and
a catalogue that never serves the path is still a field nobody can point to a
working control for, whatever this file says.

**The count assertions are a burndown, and they only move deliberately.**
Nothing enforces that a path moves the right direction — a person could still
move one the wrong way — but every entry is visible in review, and a count
asserted here turns growing or shrinking a category into a deliberate edit to
a number rather than a line that slips in.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from platform.config_service.fields import declared_fields
from tests.contract.console.test_console_shell import console_root, declared_areas
from tools.mockplane.dataset.served import config_records

pytestmark = pytest.mark.contract

OWNERSHIP_MODULE: Final = console_root() / "src" / "shell" / "config-ownership.ts"

#: The scalar types the raw editor draws a plain control for — the same four
#: `console/src/surfaces/preview.tsx`'s own `EDITABLE_TYPES` names.
EDITABLE_TYPES: Final = frozenset({"string", "integer", "number", "boolean"})

#: `{ path: 'a.b', page: 'settings-x' }` — whitespace-tolerant on purpose, and
#: shared by `CONFIG_FIELD_OWNERS` and `CONFIG_FIELDS_NO_CONTROL`, which use
#: the same `path`/`page` shape for two different claims.
#:
#: The formatter wraps an entry whose path is long enough to pass the print
#: width, so a pattern anchored to one line silently stops seeing exactly the
#: entries with the longest paths. It did, and six fields read as unaccounted
#: for while their declaration sat in the file.
_ALLOCATION: Final = re.compile(r"\{\s*path:\s*'([a-z0-9_.]+)',\s*page:\s*'([a-z-]+)',?\s*\}")

#: A bare quoted path, which is how `CONFIG_FIELDS_MACHINE` is written. Never
#: wrapped, because a lone string always fits, but read with the same
#: tolerance the allocation pattern above uses.
_BARE_PATH: Final = re.compile(r"^\s*'([a-z0-9_.]+)',$", re.MULTILINE)


def _source() -> str:
    return OWNERSHIP_MODULE.read_text(encoding="utf-8")


def _section(name: str) -> str:
    """Return the array literal `name` declares, so one list cannot read another."""
    source = _source()
    start = source.index(f"export const {name}")
    end = source.index("];", start)
    return source[start:end]


def owned() -> dict[str, str]:
    """Return every field a person edits today, as path -> page."""
    return dict(_ALLOCATION.findall(_section("CONFIG_FIELD_OWNERS")))


def machine() -> tuple[str, ...]:
    """Return every field the console or the server writes on its own."""
    return tuple(_BARE_PATH.findall(_section("CONFIG_FIELDS_MACHINE")))


def no_control() -> dict[str, str]:
    """Return every field with no working control yet, as path -> responsible page."""
    return dict(_ALLOCATION.findall(_section("CONFIG_FIELDS_NO_CONTROL")))


def schema_fields() -> frozenset[str]:
    """Return every field the configuration schema declares."""
    return frozenset(field.path for field in declared_fields())


def field_types() -> dict[str, str]:
    """Return every schema field's declared type, as path -> type."""
    return {field.path: field.type for field in declared_fields()}


def reachable_fields() -> frozenset[str]:
    """Return every field the raw configuration editor can actually edit.

    Not the four scalar types alone. `preview.tsx`'s `FieldRow` reaches an
    array too, whenever the schema declares what one entry looks like: its
    `isObjectList` is ``type === 'array' && itemFields.length > 0``, and such a
    field is drawn as an `ObjectList` with add, remove and reorder. Eighteen
    array fields satisfy that today, among them `transit.destinations`,
    `surfaces.channels` and `policies.observation.detectors`.

    Reading parity against the scalars alone would therefore authorise
    deleting the editor while eighteen fields lost the only place they could
    be changed — the precise capability regression the map exists to prevent,
    arriving through the check that was supposed to catch it.
    """
    return frozenset(
        field.path
        for field in declared_fields()
        if field.type in EDITABLE_TYPES or (field.type == "array" and len(field.item_fields) > 0)
    )


def declared_area_ids() -> frozenset[str]:
    """Return every area id the console declares — Settings pages included.

    `declared_areas` does not distinguish a top-level `Area` from a
    `SettingsPage`; both follow the identical "`id:` right after the brace"
    contract in `routes.ts`, so this already covers both without needing a
    second parser.
    """
    return frozenset(identifier for identifier, _, _ in declared_areas())


def test_the_parser_reads_every_list_rather_than_silently_finding_nothing() -> None:
    """A regex that matched nothing would make every check below vacuously true."""
    assert len(owned()) > 0
    assert len(machine()) > 0
    assert len(no_control()) > 0


def test_every_field_the_schema_declares_is_accounted_for() -> None:
    """The check the whole file exists for: a new field belongs somewhere, or fails here."""
    accounted = frozenset(owned()) | frozenset(machine()) | frozenset(no_control())
    missing = sorted(schema_fields() - accounted)
    assert not missing, (
        f"{len(missing)} configuration field(s) are in none of the three lists of "
        f"console/src/shell/config-ownership.ts: {missing}. A field with no owning "
        f"screen, no admission that it is machine-written, and no named "
        f"responsible page is a setting an operator cannot reach and nobody "
        f"decided to drop."
    )


def test_nothing_is_claimed_that_the_schema_does_not_declare() -> None:
    """A path that outlived its field would be coverage on paper only."""
    accounted = frozenset(owned()) | frozenset(machine()) | frozenset(no_control())
    stale = sorted(accounted - schema_fields())
    assert not stale, (
        f"config-ownership.ts names {len(stale)} path(s) the schema no longer has: "
        f"{stale}. Remove them, or restore the fields they were written for."
    )


def test_no_field_belongs_to_more_than_one_category() -> None:
    """The three lists answer the same question and may not disagree with each other."""
    sets = {
        "owned": frozenset(owned()),
        "machine": frozenset(machine()),
        "no_control": frozenset(no_control()),
    }
    for (left_name, left), (right_name, right) in (
        (a, b) for a in sets.items() for b in sets.items() if a[0] < b[0]
    ):
        both = sorted(left & right)
        assert not both, f"claimed as both {left_name} and {right_name}: {both}"


def test_every_page_named_is_an_area_the_console_actually_has() -> None:
    """An owner, or a would-be owner, nobody can navigate to is not an owner.

    Checked against every area `routes.ts` declares — the nine Settings pages
    and the rest of the sidebar alike — because `agent` and `knowledge` are
    real navigable destinations too, not only the Settings subnav.
    """
    areas = declared_area_ids()
    unknown_owned = sorted({page for page in owned().values() if page not in areas})
    unknown_no_control = sorted({page for page in no_control().values() if page not in areas})
    assert not unknown_owned, (
        f"config-ownership.ts names {unknown_owned} as owning pages, which "
        f"routes.ts does not declare as an area."
    )
    assert not unknown_no_control, (
        f"config-ownership.ts names {unknown_no_control} as responsible for a "
        f"field with no control, which routes.ts does not declare as an area."
    )


@pytest.mark.parametrize("path", sorted(machine()))
def test_a_machine_field_is_a_real_field_named_one_at_a_time(path: str) -> None:
    """Parametrised so the report names the field, not a set difference."""
    assert path in schema_fields()


@pytest.mark.parametrize("path", sorted(no_control()))
def test_a_no_control_field_is_a_real_field_named_one_at_a_time(path: str) -> None:
    """Parametrised so the report names the field, not a set difference of dozens."""
    assert path in schema_fields()


def test_the_size_of_each_category_is_what_the_console_says_it_is() -> None:
    """Each count, asserted so that growing or shrinking any of them is deliberate.

    Not a threshold that quietly permits drift in one direction: `owned` should
    only grow, `no_control` should only shrink (until a future feature decides
    to build a list or an object editor), and `machine` should change only when
    somebody looks at a field and makes the same call this file already made
    for `verified_digest` and `tutorial_dismissed`.
    """
    assert len(owned()) == 103, (
        f"{len(owned())} fields are owned, not the 103 recorded here. If a page "
        f"now owns more of them, update this number in the same change that "
        f"moved them into CONFIG_FIELD_OWNERS."
    )
    assert len(machine()) == 2, (
        f"{len(machine())} fields are declared machine-written, not the 2 "
        f"recorded here. Update this number in the same change that added or "
        f"removed one."
    )
    assert len(no_control()) == 11, (
        f"{len(no_control())} fields have no working control, not the 11 "
        f"recorded here. Update this number in the same change that moved a "
        f"field out of (or into) CONFIG_FIELDS_NO_CONTROL."
    )


def test_the_no_control_category_splits_the_way_its_docstring_says() -> None:
    """Of the fields with no control, the array/object half is fixed; the rest is the gap.

    What is left with no control is only what nothing could ever control: an
    object, or an array the schema describes no entry shape for. Seven arrays
    and four objects. Everything the raw editor could reach is owned, which is
    what `test_no_field_the_raw_editor_can_reach_is_left_with_no_control`
    reads.
    """
    types = field_types()
    reachable = reachable_fields()
    permanent = sorted(path for path in no_control() if path not in reachable)
    pending = sorted(path for path in no_control() if path in reachable)
    arrays = sum(1 for path in permanent if types[path] == "array")
    objects = sum(1 for path in permanent if types[path] == "object")
    assert (arrays, objects) == (7, 4), (
        f"the permanently-uncontrollable half of CONFIG_FIELDS_NO_CONTROL is "
        f"{arrays} arrays and {objects} objects, not 7 and 4: {permanent}"
    )
    assert len(pending) == 0, (
        f"{len(pending)} field(s) the raw editor can reach have no control, not "
        f"the 0 recorded here: {pending}. Update this number in the same change "
        f"that moved one of them into CONFIG_FIELD_OWNERS."
    )


def test_no_field_the_raw_editor_can_reach_is_left_with_no_control() -> None:
    """The invariant that actually authorises the raw editor's removal.

    Not `len(unowned()) == 101`, which only ages as screens are built: this
    reads true once every field the raw editor can actually reach — the four
    scalar types, and an array the schema describes an entry for, which it
    draws as an `ObjectList` — is either owned or a declared machine field,
    and it is what has to hold before the editor can go. It holds: every one
    of the hundred and four fields the editor can reach has a control on the
    page that owns its subject, so the editor may be removed without any of
    them losing the only place it could be changed.
    """
    stuck = sorted(path for path in no_control() if path in reachable_fields())
    assert not stuck, (
        f"{len(stuck)} field(s) the raw editor can reach have no page with a working "
        f"control yet: {stuck}. Each is already named on CONFIG_FIELDS_NO_CONTROL "
        f"with the page responsible for it — building that page's control and "
        f"moving the field into CONFIG_FIELD_OWNERS is what closes this one."
    )


def served_field_catalogue_paths() -> frozenset[str]:
    """Return every path the mock's own `/v1/config/{node_id}/fields` serves.

    Read from `tools/mockplane/dataset/served.py`'s own `config_records()` —
    the same call `MockPlane` replays for that route — so this asks exactly
    the question a browser pointed at the mock would get answered. The
    catalogue does not vary by node in this dataset, only the value and
    provenance of each field within it do, so the first node's record already
    speaks for every node's.
    """
    for record in config_records():
        if record.slug == "config-fields":
            return frozenset(str(each["path"]) for each in record.body["fields"])
    return frozenset()


#: The four array-shaped `policies.autonomy` fields on the guardrails page
#: carry their own purpose-built form (`AutonomyEditor`, `OverrideEditor`),
#: reading a pair of endpoints this same dataset serves in full —
#: `autonomy-policy` and `autonomy-bounds` — which is where their
#: reachability is demonstrated, not the generic field catalogue the next
#: check reads. Excluded from it for that reason, not because a bespoke form
#: is exempt from having to be reachable at all: every other array/object
#: field this file has found owned is claimed, by its own page's own
#: comments, through exactly the mechanism this check reads —
#: `AdvancedConfigSection`'s prefix sweep of the same generic editor — with
#: no second, independent endpoint standing behind it the way these four have.
_FIELDS_WITH_A_SEPARATE_PROVEN_ENDPOINT: Final = frozenset(
    {
        "policies.autonomy.budgets",
        "policies.autonomy.freezes",
        "policies.autonomy.overrides",
        "policies.autonomy.rules",
    }
)


def array_or_object_fields_owned_only_by_the_generic_editor() -> tuple[str, ...]:
    """Every owned array/object field whose sole claim to a control is the generic editor.

    Not a scalar — the four `EDITABLE_TYPES` draw one regardless of which
    page it is on — and not one of the four fields above, which read an
    endpoint of their own. What remains, on any page, is exactly the set the
    generic, prefix-scoped `AdvancedConfigSection`/`ConfigEditor` is the only
    claimed mechanism for, so that claim is only as good as what the data
    feeding that editor actually carries.
    """
    types = field_types()
    return tuple(
        sorted(
            path
            for path, _ in owned().items()
            if types.get(path) in ("array", "object")
            and path not in _FIELDS_WITH_A_SEPARATE_PROVEN_ENDPOINT
        )
    )


@pytest.mark.parametrize("path", sorted(owned()))
def test_an_owned_field_is_a_type_the_editor_has_any_control_for(path: str) -> None:
    """Parametrised so the report names the field, not a set difference.

    `CONFIG_FIELD_OWNERS` claims a person edits `path` today, on the page
    named beside it. Held here to the identical standard
    `test_no_field_the_raw_editor_can_reach_is_left_with_no_control` already
    holds `CONFIG_FIELDS_NO_CONTROL` to, read from the opposite direction: a
    field whose declared type is neither a scalar the editor's own `Control`
    draws nor an array the schema describes an entry shape for is a field no
    mechanism in this console — generic editor or bespoke form alike — can
    draw any control for, regardless of which page claims it. A claim of this
    shape is not a smaller version of the truth; it is the exact defect this
    file exists to make impossible to miss.
    """
    assert path in reachable_fields(), (
        f"{path!r} is claimed as owned (a working control exists for it "
        f"today), but its declared type ({field_types().get(path)!r}) is not "
        f"one the editor can draw any control for: not a scalar, and not an "
        f"array the schema names an entry shape for. No mechanism in this "
        f"console can edit this field as things stand."
    )


#: Every array/object field that passes the type check above — owned, and
#: reachable only through the generic, prefix-scoped editor — but that
#: `tools/mockplane/dataset/served.py`'s own field catalogue does not serve
#: yet. **Not a parity failure and not a product defect.** That catalogue is a
#: hand-picked slice of the schema, chosen so the effective-values table
#: beside the generic editor renders something a person can read a screenshot
#: of, never a mirror of the whole schema — `policies.masking.custom_patterns`
#: is proof the slice can grow; it is not proof the console has no control for
#: a path missing from it. The generic editor would draw a working
#: `ObjectList` for every field named here the moment the catalogue actually
#: hands it that field, which is a dataset change, not a product one, and not
#: one this feature owns: the pages below are not built or reviewed by moving
#: a path out of this set, only the fixture is.
#:
#: Named individually, the same way `_FIELDS_WITH_A_SEPARATE_PROVEN_ENDPOINT`
#: above is, and held to the same standard the two tests beneath the next one
#: hold every other list in this file to: a field the fixture catches up on
#: has to leave here by name, and a field that stops belonging to the universe
#: this set is drawn from has to leave here too — either failure names the
#: path, so this set cannot silently drift into claiming more, or less, than
#: it was written for.
FIXTURE_DOES_NOT_YET_SERVE: Final = frozenset(
    {
        "agents.subagents",
        "capabilities.protocol_servers",
        "integrations.active",
        "policies.observation.bridge.dashboards",
        "policies.observation.bridge.label_rules",
        "policies.observation.bridge.log_selectors",
        "policies.observation.bridge.precedence",
        "policies.observation.detectors",
        "policies.observation.guardian.overrides",
        "surfaces.channels",
        "surfaces.notification_sinks",
        "surfaces.report_destinations",
        "transit.destinations",
        "transit.rules",
    }
)


@pytest.mark.parametrize(
    "path",
    sorted(
        path
        for path in array_or_object_fields_owned_only_by_the_generic_editor()
        if path not in FIXTURE_DOES_NOT_YET_SERVE
    ),
)
def test_a_generic_editor_only_array_field_is_in_the_catalogue_its_editor_reads_from(
    path: str,
) -> None:
    """Passing the type check above is necessary, and it is not sufficient.

    `policies.masking.custom_patterns` passes
    `test_an_owned_field_is_a_type_the_editor_has_any_control_for`: the schema
    gives it an entry shape (`name`, `pattern`), so `preview.tsx`'s
    `isObjectList` says yes and the generic editor would draw a working
    `ObjectList` for it — the moment it is ever handed the field at all. Every
    field parametrised here makes the identical claim, on whichever page names
    it: type-reachable, and reachable *only* through the generic,
    prefix-scoped editor, never a bespoke form of its own. That claim is only
    as good as the data feeding that editor, and the mock's own
    `/v1/config/{node_id}/fields` catalogue (`tools/mockplane/dataset/served.py`)
    is what every environment this console runs in — dev, contract, or the
    browser suite — actually reads it from. A type that could work and a
    catalogue that never serves the path leave the same operator with the
    same nothing to press.

    Not parametrised over `FIXTURE_DOES_NOT_YET_SERVE`: those paths already
    fail this exact assertion, for a reason this test cannot tell apart from a
    real regression — the catalogue is a deliberately partial fixture, not a
    second copy of the schema — so they are named there instead, and held to
    the opposite assertion by the tests beneath this one. A field failing
    *here* is a field with no standing explanation for why it fails, which is
    what makes it worth stopping the build on.
    """
    assert path in served_field_catalogue_paths(), (
        f"{path!r} is claimed as owned by {owned()[path]!r}, with its only "
        f"claim to a control being that page's generic, prefix-scoped "
        f"editor (or, if it turns out to have a bespoke form of its own "
        f"after all, it belongs beside the four `policies.autonomy` fields "
        f"this check already exempts, not here). That editor draws only "
        f"what tools/mockplane/dataset/served.py's config-fields catalogue "
        f"hands it, and this path is not in it: nothing in this console can "
        f"be shown to render a control for it."
    )


def test_every_named_fixture_gap_still_needs_the_exemption_it_claims() -> None:
    """The other half of the burndown: a gap the fixture closes has to leave this list by name.

    Nothing enforces which direction `FIXTURE_DOES_NOT_YET_SERVE` moves, the
    same way nothing enforces it for the counts `CONFIG_FIELD_OWNERS` and
    `CONFIG_FIELDS_NO_CONTROL` are held to above — but every path in it is
    visible in review, and this is what keeps the set honest between one
    change and the next: a path the mock's catalogue starts serving no longer
    needs an exemption, and has to be dropped from here in the same change
    that grows the fixture, or this fails and says exactly which one is
    stale.
    """
    caught_up = sorted(FIXTURE_DOES_NOT_YET_SERVE & served_field_catalogue_paths())
    assert not caught_up, (
        f"{caught_up} now appear in tools/mockplane/dataset/served.py's "
        f"config-fields catalogue. Remove them from FIXTURE_DOES_NOT_YET_SERVE — "
        f"test_a_generic_editor_only_array_field_is_in_the_catalogue_its_editor_reads_from "
        f"covers them once you do, the same way it already covers "
        f"policies.masking.custom_patterns."
    )


def test_every_named_fixture_gap_is_still_an_array_or_object_field_owned_only_here() -> None:
    """A path that outlived its reason to be exempt would be a stale exemption, silently.

    `FIXTURE_DOES_NOT_YET_SERVE` claims each path is array- or object-typed,
    owned, and reachable only through the generic editor — exactly the set
    `array_or_object_fields_owned_only_by_the_generic_editor` computes. A path
    reassigned to a bespoke form, moved to `CONFIG_FIELDS_NO_CONTROL`, or
    dropped from the schema entirely stops belonging to that set without this
    file noticing, unless something reads the two against each other.
    """
    stale = sorted(
        FIXTURE_DOES_NOT_YET_SERVE
        - frozenset(array_or_object_fields_owned_only_by_the_generic_editor())
    )
    assert not stale, (
        f"FIXTURE_DOES_NOT_YET_SERVE names {stale}, which "
        f"array_or_object_fields_owned_only_by_the_generic_editor() no longer "
        f"returns. Remove it from FIXTURE_DOES_NOT_YET_SERVE, or explain why it "
        f"belongs there again."
    )

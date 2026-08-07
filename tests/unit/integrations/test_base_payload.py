"""Reading a vendor's answer without trusting its shape.

Every one of the catalogue's clients parses a JSON document a vendor sent, and
every one of them is one renamed key away from a ``KeyError`` raised a long way
from the cause. These are the readers that turn that into an empty answer the
capability can report honestly.
"""

from __future__ import annotations

import pytest

from integrations._base.payload import (
    counted,
    dig,
    named,
    records,
    tabular,
    text,
    xml_records,
    xml_text,
)

pytestmark = pytest.mark.unit


class TestDig:
    def test_it_walks_a_nested_document(self) -> None:
        assert dig({"meta": {"page": {"after": "c2"}}}, "meta", "page", "after") == "c2"

    def test_a_missing_key_is_none_rather_than_an_error(self) -> None:
        assert dig({"meta": {}}, "meta", "page", "after") is None

    def test_a_non_mapping_on_the_way_down_is_none(self) -> None:
        """An error body has the same content type as a successful one."""
        assert dig({"meta": "forbidden"}, "meta", "page") is None

    def test_an_empty_path_returns_the_document(self) -> None:
        assert dig({"a": 1}) == {"a": 1}


class TestRecords:
    def test_it_returns_the_list_at_the_path(self) -> None:
        found = records({"data": {"results": [{"id": "1"}, {"id": "2"}]}}, "data", "results")

        assert found == ({"id": "1"}, {"id": "2"})

    def test_a_missing_list_is_empty_rather_than_an_error(self) -> None:
        assert records({"data": {}}, "data", "results") == ()

    def test_entries_that_are_not_mappings_are_dropped(self) -> None:
        """A vendor mixing nulls into a result array should not end the call."""
        assert records({"items": [{"id": "1"}, None, "x"]}, "items") == ({"id": "1"},)

    def test_a_bare_list_at_the_root_is_read_with_an_empty_path(self) -> None:
        assert records([{"id": "1"}]) == ({"id": "1"},)


class TestText:
    def test_it_returns_the_value_as_a_string(self) -> None:
        assert text({"cursor": 12}, "cursor") == "12"

    def test_a_missing_value_is_the_empty_string(self) -> None:
        assert text({}, "cursor") == ""

    def test_a_blank_value_stays_blank_so_a_walk_terminates(self) -> None:
        """A cursor read as ``"None"`` would page forever."""
        assert text({"cursor": None}, "cursor") == ""


class TestTabular:
    ANSWER = {
        "meta": {"rowType": [{"name": "user"}, {"name": "state"}]},
        "data": [["reports", "RUNNING"], ["app", "BLOCKED"]],
    }

    def test_rows_become_mappings_keyed_by_column_name(self) -> None:
        found = tabular(self.ANSWER, "meta.rowType", "data")

        assert found == (
            {"user": "reports", "state": "RUNNING"},
            {"user": "app", "state": "BLOCKED"},
        )

    def test_a_row_shorter_than_the_columns_is_kept_partial(self) -> None:
        """A partial record is still evidence; raising here would end the turn."""
        answer = {"meta": {"rowType": [{"name": "a"}, {"name": "b"}]}, "data": [["x"]]}

        assert tabular(answer, "meta.rowType", "data") == ({"a": "x"},)

    def test_rows_that_are_already_mappings_pass_through(self) -> None:
        answer = {"meta": {"rowType": []}, "data": [{"user": "reports"}]}

        assert tabular(answer, "meta.rowType", "data") == ({"user": "reports"},)

    def test_a_missing_answer_is_empty_rather_than_an_error(self) -> None:
        assert tabular({}, "meta.rowType", "data") == ()


class TestNamed:
    def test_a_list_of_identifiers_becomes_one_record_each(self) -> None:
        found = named({"clusters": ["prod", "staging"]}, "clusters", key="cluster")

        assert found == ({"cluster": "prod"}, {"cluster": "staging"})

    def test_a_missing_list_is_empty(self) -> None:
        assert named({}, "clusters") == ()

    def test_entries_that_are_not_identifiers_are_dropped(self) -> None:
        assert named({"a": ["x", {"y": 1}, None]}, "a") == ({"name": "x"},)


class TestXmlRecords:
    DOCUMENT = """<?xml version="1.0"?>
    <DescribeInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
      <reservationSet>
        <item>
          <instanceId>i-1</instanceId>
          <instanceState><name>running</name></instanceState>
        </item>
        <item>
          <instanceId>i-2</instanceId>
          <instanceState><name>stopped</name></instanceState>
        </item>
      </reservationSet>
    </DescribeInstancesResponse>"""

    def test_it_returns_one_mapping_per_matching_element(self) -> None:
        found = xml_records(self.DOCUMENT, "item")

        assert len(found) == 2
        assert found[0]["instanceId"] == "i-1"

    def test_nested_elements_are_flattened_under_their_own_tag(self) -> None:
        """A dotted grouping field then reaches them the same way JSON's does."""
        found = xml_records(self.DOCUMENT, "item")

        assert found[0]["instanceState"] == {"name": "running"}

    def test_a_namespace_prefix_is_ignored_because_vendors_change_theirs(self) -> None:
        assert xml_records(self.DOCUMENT, "reservationSet")[0]

    def test_a_body_that_is_not_xml_is_empty_rather_than_an_error(self) -> None:
        """An error page and a successful answer arrive with the same content type."""
        assert xml_records("<html>gateway timeout", "item") == ()

    def test_a_tag_that_does_not_occur_is_empty(self) -> None:
        assert xml_records(self.DOCUMENT, "nothing") == ()

    def test_a_token_element_is_read_as_text(self) -> None:
        assert xml_text("<r><nextToken>abc</nextToken></r>", "nextToken") == "abc"

    def test_an_absent_token_is_blank_so_the_walk_terminates(self) -> None:
        assert xml_text(self.DOCUMENT, "nextToken") == ""

    def test_an_unparseable_body_yields_no_token(self) -> None:
        assert xml_text("<html>", "nextToken") == ""


class TestCounted:
    def test_it_groups_records_by_one_field(self) -> None:
        found = counted(
            ({"status": "error"}, {"status": "error"}, {"status": "info"}),
            "status",
        )

        assert found == ({"by": "error", "count": 2}, {"by": "info", "count": 1})

    def test_it_orders_by_count_so_the_largest_group_leads(self) -> None:
        found = counted(({"s": "a"}, {"s": "b"}, {"s": "b"}), "s")

        assert found[0] == {"by": "b", "count": 2}

    def test_a_record_missing_the_field_is_grouped_as_unknown(self) -> None:
        """Dropping it would understate the total, which is the number read back."""
        assert counted(({"other": 1},), "status") == ({"by": "unknown", "count": 1},)

    def test_a_nested_field_is_read_by_dotted_path(self) -> None:
        found = counted(({"attributes": {"service": "checkout"}},), "attributes.service")

        assert found == ({"by": "checkout", "count": 1},)

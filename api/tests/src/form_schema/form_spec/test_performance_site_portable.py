"""Project/Performance Site is a portable repeating-site canary, not a registered form."""

import json
from collections.abc import Iterator
from typing import Any

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form


def _walk(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)


def test_performance_site_loads_without_form_specific_adapter_code() -> None:
    projected = load_form("performance-site")
    fields = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "field"]

    assert projected.meta["formName"] == "Project/Performance Site Location(s)"
    assert projected.meta["formVersion"] == "4.0"
    assert projected.meta["legacyFormId"] == 723
    assert list(projected.form_json_schema["properties"]) == [
        "primary_site",
        "additional_sites",
        "additional_locations",
    ]
    assert projected.form_json_schema["properties"]["additional_sites"]["maxItems"] == 299
    address = projected.form_json_schema["$defs"]["PerformanceSiteAddress"]
    assert any(
        branch.get("then", {}).get("properties", {}).get("zip_code") == {"minLength": 9}
        for branch in address["allOf"]
    )
    primary = projected.form_json_schema["$defs"]["PrimaryPerformanceSiteDetails"]
    assert any(
        branch.get("then", {}).get("required") == ["organization_name"]
        for branch in primary["allOf"]
    )
    assert len(fields) == 25


def test_repeating_site_conditions_retain_row_scope() -> None:
    projected = load_form("performance-site")
    conditional = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]
    root = [node for node in conditional if node["conditional"]["when"]["ref"]["scope"] == "root"]
    item = [node for node in conditional if node["conditional"]["when"]["ref"]["scope"] == "item"]

    assert len(root) == 3
    assert len(item) == 2
    assert {node["conditional"]["when"]["ref"]["pointer"] for node in item} == {"/address/country"}
    overflow = next(
        node for node in conditional if node.get("definition") == "/properties/additional_locations"
    )
    assert overflow["conditional"]["when"] == {
        "op": "countAtLeast",
        "ref": {"scope": "root", "pointer": "/additional_sites"},
        "minimum": 299,
    }
    additional_sites = next(
        node
        for node in _walk(projected.form_ui_schema)
        if node.get("type") == "fieldList" and node.get("name") == "additional_sites"
    )
    assert additional_sites["validateBeforeAdd"] is True
    assert projected.form_rule_schema == {
        "additional_locations": {"gg_validation": {"rule": "attachment"}}
    }
    assert projected.json_to_xml_schema is not None
    assert projected.json_to_xml_schema["primary_site"]["xml_transform"]["target"] == "PrimarySite"


def test_performance_site_evidence_and_release_gates_remain_explicit() -> None:
    root = ARTIFACTS / "forms" / "performance-site"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())

    assert evidence["extraction"]["revision"] == "4312f6504b060e2b9ffdbd2307fc41130c3123a0"
    assert evidence["extraction"]["sourceSetSha256"] == (
        "ba3348472c48a2fac951308c9a8f44fc078c5b014771d7e9d1a4b0521a00d879"
    )
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert manifest["artifacts"]["targets/grants-gov-xml.json"] == "generated"

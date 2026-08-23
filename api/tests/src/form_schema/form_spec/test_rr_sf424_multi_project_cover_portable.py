"""R&R Multi-Project Cover is a portable sibling canary, not a registered form."""

import json
from collections.abc import Iterator
from typing import Any

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form


def _walk(nodes: list[object]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            yield from _walk(children)


def test_multi_project_cover_loads_without_form_specific_adapter_code() -> None:
    projected = load_form("rr-sf424-multi-project-cover")
    fields = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "field"]

    assert projected.meta == {
        "id": "rr-sf424-multi-project-cover",
        "legacyFormId": 769,
        "formName": "[Draft] Research & Related Multi-Project Cover",
        "shortFormName": "RR_SF424_Multi_Project_Cover_4_0",
        "formVersion": "4.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
    }
    assert len(projected.form_json_schema["properties"]) == 28
    assert "required" not in projected.form_json_schema
    assert len(projected.form_ui_schema) == 21
    assert len(fields) == 106


def test_multi_project_conditions_cross_the_naming_boundary_with_typed_effects() -> None:
    projected = load_form("rr-sf424-multi-project-cover")
    conditional = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]

    assert len(conditional) == 14
    assert (
        sum(node["conditional"]["then"].get("interaction") == "enabled" for node in conditional)
        == 10
    )
    assert (
        sum(node["conditional"]["then"].get("interaction") == "readOnly" for node in conditional)
        == 4
    )
    assert (
        sum(
            node["conditional"]["otherwise"].get("interaction") == "disabled"
            for node in conditional
        )
        == 10
    )
    assert (
        sum(
            node["conditional"]["otherwise"].get("interaction") == "enabled" for node in conditional
        )
        == 4
    )
    assert all(
        "enabled" not in outcome and "readOnly" not in outcome
        for node in conditional
        for outcome in (node["conditional"]["then"], node["conditional"]["otherwise"])
    )
    assert {node["conditional"]["when"]["ref"]["pointer"] for node in conditional} >= {
        "/applicant_info/organization_info/address/country",
        "/applicant_type/applicant_type_code",
        "/application_type/application_type_code",
        "/authorized_representative/address/country",
    }
    assert all(
        segment == segment.lower()
        for node in conditional
        for segment in node["conditional"]["when"]["ref"]["pointer"].split("/")
        if segment
    )


def test_multi_project_lifecycle_is_not_inferred_from_standalone_cover() -> None:
    projected = load_form("rr-sf424-multi-project-cover")
    rules = projected.form_rule_schema

    assert rules is not None
    assert set(rules) == {
        "sflll_attachment",
        "pre_application_attachment",
        "cover_letter_attachment",
    }
    assert "submitted_date" not in rules
    assert "aor_signature" not in rules
    assert "aor_signed_date" not in rules


def test_multi_project_evidence_remains_unreviewed_and_xml_is_an_explicit_gate() -> None:
    root = ARTIFACTS / "forms" / "rr-sf424-multi-project-cover"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())

    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "c1573287e0664d7b991e69c352038534b771189f",
        "artifact": "artifacts/proof/grantsgov-RRSF424MPCover.jsonl.manifest.json",
        "sourceSetSha256": "3224ce9eac55ccc27a8cae4f257efe10b69872ef5bb6c3fa22d82c9ed4427fac",
        "extractedAt": "2026-08-22T22:34:16.759448Z",
    }
    review = evidence["semanticReview"]
    assert review["status"] == "proposed"
    assert {
        "#/properties/stateReceivedDate",
        "#/properties/stateId",
        "#/properties/agencyRoutingNumber",
        "#/properties/grantsTrackingNumber",
    }.issubset({mapping["canonicalPointer"] for mapping in review["mappings"]})
    assert all(mapping["status"] == "proposed" for mapping in review["mappings"])
    assert "xml-schema.json" not in manifest["artifacts"]

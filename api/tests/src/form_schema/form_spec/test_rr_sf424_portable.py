"""R&R SF-424 conformance canary for the portable form specification.

The package is intentionally not registered as a runtime form yet. Exact XML output and
the remaining source-review gates must become declarative before it can replace a
production implementation.
"""

import json

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form


def _walk(nodes: list[object]):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            yield from _walk(children)


def test_rr_sf424_loads_as_a_complete_structural_canary() -> None:
    projected = load_form("rr-sf424")
    nodes = list(_walk(projected.form_ui_schema))

    assert projected.meta == {
        "id": "rr-sf424",
        "formId": "98f03cc4-5cd8-455b-a318-ba5abd0cf572",
        "legacyFormId": 768,
        "formName": "[Draft] Research & Related Application for Federal Assistance (SF424 R&R)",
        "shortFormName": "RR_SF424_5_0",
        "formVersion": "5.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
        "formType": "RRSF424",
        "sggVersion": "1.0",
    }
    assert len(projected.form_json_schema["properties"]) == 28
    assert len(projected.form_json_schema["allOf"]) == 4
    assert len(projected.form_ui_schema) == 21
    assert sum(node.get("type") in {"field", "null"} for node in nodes) == 106


def test_rr_sf424_conditionals_cross_the_adapter_naming_boundary() -> None:
    projected = load_form("rr-sf424")
    conditional_nodes = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]

    assert len(conditional_nodes) == 8
    pointers = {node["conditional"]["when"]["ref"]["pointer"] for node in conditional_nodes}
    assert "/submission_type_code" in pointers
    assert "/applicant_type/applicant_type_code" in pointers
    assert "/application_type/application_type_code" in pointers
    assert "/state_review/state_review_code_type" in pointers
    assert all("_" in segment for pointer in pointers for segment in pointer.split("/") if segment)


def test_rr_sf424_revision_choices_preserve_the_encoded_wire_contract() -> None:
    projected = load_form("rr-sf424")
    revision = projected.form_json_schema["properties"]["application_type"]["properties"][
        "revision_code"
    ]
    revision_enum = projected.form_json_schema["$defs"]["ResearchRevisionCode"]["enum"]

    assert revision_enum == ["A", "B", "C", "D", "E", "AC", "AD", "BC", "BD"]
    assert revision["x-encoded-checkbox-group"] == {
        "choices": [
            {"code": "A", "label": "A. Increase Award"},
            {"code": "B", "label": "B. Decrease Award"},
            {"code": "C", "label": "C. Increase Duration"},
            {"code": "D", "label": "D. Decrease Duration"},
            {"code": "E", "label": "E. Other"},
        ],
        "combinations": [
            {"value": "A", "members": ["A"]},
            {"value": "B", "members": ["B"]},
            {"value": "C", "members": ["C"]},
            {"value": "D", "members": ["D"]},
            {"value": "E", "members": ["E"]},
            {"value": "AC", "members": ["A", "C"]},
            {"value": "AD", "members": ["A", "D"]},
            {"value": "BC", "members": ["B", "C"]},
            {"value": "BD", "members": ["B", "D"]},
        ],
    }


def test_rr_sf424_evidence_stays_source_bound_and_semantically_unaccepted() -> None:
    evidence = json.loads((ARTIFACTS / "forms" / "rr-sf424" / "evidence.json").read_text())

    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef",
        "artifact": "artifacts/proof/grantsgov-RRSF424.jsonl.manifest.json",
        "sourceSetSha256": "81ad602bf94391d4a7db80558802288452848aef97e68d4ca4ad1fe3d4b7e035",
        "extractedAt": "2026-08-18T16:54:29.252851Z",
    }
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert [(source["type"], source["sha256"]) for source in evidence["sources"]] == [
        ("dat", "532938a75c587bdc8813fd3af625be4338281d0491999fc39aeaaac51b79c9c1"),
        ("xsd", "f140f32afed9d7efbe30fc8f299542bbbc3121dbc87a79aa351fcf096163d3bc"),
        ("xsd", "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d"),
        ("xsd", "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb"),
        ("xsd", "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8"),
        ("xsd", "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a"),
    ]


def test_rr_sf424_remains_unregistered_until_xml_is_declarative() -> None:
    manifest = json.loads((ARTIFACTS / "forms" / "rr-sf424" / "manifest.json").read_text())

    assert "xml-schema.json" not in manifest["artifacts"]

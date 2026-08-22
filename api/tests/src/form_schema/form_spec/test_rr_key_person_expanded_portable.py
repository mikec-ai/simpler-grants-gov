"""R&R Senior/Key Person is a portable repeating-person canary, not a registered form."""

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


def test_key_person_loads_without_form_specific_adapter_code() -> None:
    projected = load_form("rr-key-person-expanded")
    fields = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "field"]

    assert projected.meta == {
        "id": "rr-key-person-expanded",
        "formId": "2a638e46-7680-55ba-a11a-4d152f37ca1e",
        "legacyFormId": 774,
        "formName": "Research & Related Senior/Key Person Profile (Expanded)",
        "shortFormName": "RR_KeyPersonExpanded_4_0",
        "formVersion": "4.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
        "formType": "RRKeyPersonExpanded",
        "sggVersion": "1.0",
    }
    assert list(projected.form_json_schema["properties"]) == [
        "principal_investigator",
        "senior_key_persons",
        "additional_profiles",
        "additional_biographical_sketches",
        "additional_current_pending_support",
    ]
    assert projected.form_json_schema["properties"]["senior_key_persons"]["maxItems"] == 99
    assert len(fields) == 57


def test_repeated_person_conditions_use_current_item_scope() -> None:
    projected = load_form("rr-key-person-expanded")
    conditional = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]
    root = [node for node in conditional if node["conditional"]["when"]["ref"]["scope"] == "root"]
    item = [node for node in conditional if node["conditional"]["when"]["ref"]["scope"] == "item"]

    assert len(root) == 3
    assert len(item) == 3
    assert {node["conditional"]["when"]["ref"]["pointer"] for node in item} == {
        "/address/country",
        "/project_role",
    }
    other_role = next(node for node in item if node["conditional"]["when"]["op"] == "in")
    assert other_role["conditional"]["when"]["values"] == [
        "Other Professional",
        "Other (Specify)",
    ]


def test_person_attachments_compile_while_overflow_semantics_stay_review_gated() -> None:
    projected = load_form("rr-key-person-expanded")
    attachment_rules = [
        node
        for node in _walk(projected.form_rule_schema)
        if node.get("gg_validation", {}).get("rule") == "attachment"
    ]
    assert len(attachment_rules) == 7

    root = ARTIFACTS / "forms" / "rr-key-person-expanded"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "artifact": "artifacts/proof/grantsgov-RRKeyPersonExpanded.jsonl.manifest.json",
        "sourceSetSha256": "8866396d99e32eeec6618ea63c52c2b205718dc481482b27ab61699ecd2efeb0",
        "extractedAt": "2026-08-18T16:54:30.352133Z",
    }
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert "xml-schema.json" not in manifest["artifacts"]

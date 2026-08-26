"""PHS Inclusion Enrollment is a repeated dimensional-report canary."""

import json
from collections.abc import Iterator
from typing import Any

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form

FORM_ID = "phs-inclusion-enrollment-report"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID


def _walk(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)


def test_inclusion_enrollment_loads_without_form_specific_adapter_code() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=True)
    fields = [
        node
        for node in _walk(projected.form_ui_schema)
        if node.get("type") in {"field", "input", "readOnly"}
        and isinstance(node.get("definition"), str)
    ]
    lists = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "fieldList"]
    tables = [node for node in _walk(projected.form_ui_schema) if node.get("widget") == "Table"]

    assert projected.meta["formName"] == "PHS Inclusion Enrollment Report"
    assert projected.meta["formVersion"] == "1.0"
    assert projected.meta["legacyFormId"] == 791
    assert len(fields) == 121
    assert [table["name"] for table in tables] == ["planned", "cumulativeActual"]
    assert sum(node["type"] == "readOnly" for node in fields) == 28
    assert len(lists) == 1
    assert lists[0]["name"] == "reports"
    assert lists[0]["definition"] == "/properties/reports"
    assert projected.form_json_schema["properties"]["reports"]["minItems"] == 1
    assert projected.form_json_schema["properties"]["reports"]["maxItems"] == 20
    assert projected.form_rule_schema is None
    assert projected.json_to_xml_schema is not None


def test_inclusion_enrollment_preserves_exact_sources_and_open_behavior_gates() -> None:
    evidence = json.loads((FORM_ROOT / "evidence.json").read_text())
    sources = {source["id"]: source for source in evidence["sources"]}
    calculations = [
        record for record in evidence["behaviorEvidence"] if record["ruleKind"] == "calculation"
    ]

    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "924f37b288dea3ae005986a1ba1ee182e1ddb1f6",
        "artifact": (
            "artifacts/portfolio/behavior-bindings/" "PHSInclusionEnrollmentReport-V1-0-F791.json"
        ),
        "sourceSetSha256": ("3b13a57e6407c53f1124f4a5400bed6b065d013e09cda0eaf02b6ea4bdda138a"),
        "extractedAt": "2026-08-19T17:38:44Z",
    }
    assert evidence["semanticReview"]["status"] == "proposed"
    assert sources["phs-ier-xsd-v1-0"]["sha256"] == (
        "3263bbfa8881c7d428958cf91de470cd19f0f6cbc11818c4752d5266bb0f53a4"
    )
    assert sources["phs-ier-dat-f791"]["sha256"] == (
        "31927e7673d726a76a527a4cd3ea460f7b6510c41b4010c1fb15a4a2d62995f0"
    )
    assert sources["phs-ier-readonly-pdf-f791"]["sha256"] == (
        "933c94b039e93ff6e16aae2c29a8c3fe779e1cce9334988b6fb2f5410ce6399f"
    )
    assert len(calculations) == 28
    assert len({record["canonicalPath"] for record in calculations}) == 28
    assert all(record["executionStatus"] == "source-bound-uncompiled" for record in calculations)

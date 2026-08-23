"""R&R Other Project Information is a portable policy-and-attachment canary."""

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


def test_other_project_information_loads_without_form_specific_adapter_code() -> None:
    projected = load_form("rr-other-project-information")
    fields = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "field"]
    conditions = [node for node in fields if "conditional" in node]

    assert projected.meta["formName"] == "Research & Related Other Project Information"
    assert projected.meta["formVersion"] == "1.4"
    assert projected.meta["legacyFormId"] == 619
    assert len(fields) == 26
    assert len(conditions) == 13
    assert all(node["conditional"]["when"]["ref"]["scope"] == "root" for node in conditions)
    assert conditions[0]["conditional"]["when"]["ref"]["pointer"] == (
        "/human_subjects/involves_human_subjects"
    )
    assert (
        sum(
            node.get("gg_validation", {}).get("rule") == "attachment"
            for node in _walk(projected.form_rule_schema)
        )
        == 6
    )


def test_cross_form_requirement_and_semantic_review_gates_remain_explicit() -> None:
    projected = load_form("rr-other-project-information")
    required = projected.form_json_schema["required"]
    assert "project_summary_abstract" not in required
    assert "project_narrative" not in required

    root = ARTIFACTS / "forms" / "rr-other-project-information"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    assert evidence["extraction"]["revision"] == "4312f6504b060e2b9ffdbd2307fc41130c3123a0"
    assert evidence["extraction"]["sourceSetSha256"] == (
        "c3ebbfc4870fb5be7c7afc3ad84bec0717329458745e5d36b3361de04fe79a04"
    )
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert "targets/grants-gov-xml.json" not in manifest["artifacts"]

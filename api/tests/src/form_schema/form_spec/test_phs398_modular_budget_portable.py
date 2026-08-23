"""PHS 398 Modular Budget is a portable nested-budget and calculation canary."""

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


def test_modular_budget_loads_without_form_specific_adapter_code() -> None:
    projected = load_form("phs398-modular-budget")
    fields = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "field"]
    lists = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "fieldList"]
    calculations = [
        node["gg_pre_population"]
        for node in _walk(projected.form_rule_schema)
        if "gg_pre_population" in node
    ]

    assert projected.meta["formName"] == "PHS 398 Modular Budget"
    assert projected.meta["formVersion"] == "1.2"
    assert projected.meta["legacyFormId"] == 403
    assert len(fields) == 13
    assert len(lists) == 2
    assert projected.form_json_schema["properties"]["periods"]["maxItems"] == 5
    assert len(calculations) == 8
    assert sorted(rule["order"] for rule in calculations) == list(range(1, 9))
    assert projected.form_rule_schema["periods"]["direct_costs"]["total_direct_costs"] == {
        "gg_pre_population": {
            "rule": "sum_monetary",
            "fields": [
                "@THIS.direct_cost_less_consortium_fand_a",
                "@THIS.consortium_fand_a",
            ],
            "order": 3,
        }
    }
    assert (
        sum(
            node.get("gg_validation", {}).get("rule") == "attachment"
            for node in _walk(projected.form_rule_schema)
        )
        == 3
    )


def test_modular_budget_source_and_review_gates_remain_explicit() -> None:
    root = ARTIFACTS / "forms" / "phs398-modular-budget"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())

    assert evidence["extraction"]["revision"] == "4312f6504b060e2b9ffdbd2307fc41130c3123a0"
    assert evidence["extraction"]["sourceSetSha256"] == (
        "4add1297349b180ccc7e270d98449201e1ec83f5cdbfa2eea6828c956993a8b6"
    )
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert "targets/grants-gov-xml.json" not in manifest["artifacts"]

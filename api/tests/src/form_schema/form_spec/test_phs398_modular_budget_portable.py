"""PHS 398 Modular Budget is a portable nested-budget and calculation canary."""

import json
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context


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
    tables = [
        node
        for node in _walk(projected.form_ui_schema)
        if node.get("type") == "multiField" and node.get("widget") == "Table"
    ]
    calculations = [
        node["gg_pre_population"]
        for node in _walk(projected.form_rule_schema)
        if "gg_pre_population" in node
    ]

    assert projected.meta["formName"] == "PHS 398 Modular Budget"
    assert projected.meta["formVersion"] == "1.2"
    assert projected.meta["legacyFormId"] == 403
    assert len(fields) == 18
    assert len(lists) == 2
    assert len(tables) == 1
    direct_costs_table = tables[0]
    assert direct_costs_table["name"] == "directCosts"
    assert [cell["type"] for cell in direct_costs_table["children"]["rows"][0]["cells"]] == [
        "input",
        "input",
        "readOnly",
    ]
    assert sum(column["width"] for column in direct_costs_table["children"]["columns"]) == 100
    assert projected.form_json_schema["properties"]["periods"]["maxItems"] == 5
    assert len(calculations) == 8
    assert sorted(rule["order"] for rule in calculations) == list(range(1, 9))
    calculated_definitions = {
        "/properties/periods/items/properties/direct_costs/properties/total_direct_costs",
        "/properties/periods/items/properties/indirect_costs/properties/total_indirect_costs",
        "/properties/periods/items/properties/total_direct_and_indirect_costs",
        (
            "/properties/cumulative_budget_information/properties/"
            "cumulative_direct_cost_less_consortium_fand_a"
        ),
        ("/properties/cumulative_budget_information/properties/cumulative_consortium_fand_a"),
        ("/properties/cumulative_budget_information/properties/cumulative_total_direct_costs"),
        ("/properties/cumulative_budget_information/properties/cumulative_total_indirect_costs"),
        (
            "/properties/cumulative_budget_information/properties/"
            "cumulative_total_direct_and_indirect_costs"
        ),
    }
    table_cells = [
        node
        for node in _walk(direct_costs_table["children"])
        if node.get("type") in {"input", "readOnly"}
    ]
    assert calculated_definitions <= {
        node["definition"] for node in [*fields, *table_cells] if "definition" in node
    }
    assert projected.form_rule_schema["periods"]["budget_period_end_date"]["gg_validation"] == {
        "rule": "date_not_before",
        "fields": ["@THIS.budget_period_start_date"],
    }
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
    assert projected.json_to_xml_schema is not None
    budget_justifications = projected.json_to_xml_schema["budget_justifications"]
    assert budget_justifications["xml_transform"] == {
        "target": "CummulativeBudgetInfo",
        "type": "group",
    }
    personnel = budget_justifications["justifications"]["personnel_justification"]
    assert personnel["xml_transform"] == {
        "target": "PersonnelJustification",
        "type": "group",
    }
    assert personnel["attachment"]["xml_transform"]["target"] == "attFile"


def test_modular_budget_source_and_review_gates_remain_explicit() -> None:
    root = ARTIFACTS / "forms" / "phs398-modular-budget"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())

    assert evidence["extraction"]["revision"] == "4312f6504b060e2b9ffdbd2307fc41130c3123a0"
    assert evidence["extraction"]["sourceSetSha256"] == (
        "4add1297349b180ccc7e270d98449201e1ec83f5cdbfa2eea6828c956993a8b6"
    )
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert manifest["artifacts"]["targets/grants-gov-xml.json"] == "generated"


def test_all_eight_modular_budget_calculations_execute_in_dependency_order() -> None:
    projected = load_form("phs398-modular-budget")
    data = {
        "periods": [
            {
                "direct_costs": {
                    "direct_cost_less_consortium_fand_a": "100000.00",
                    "consortium_fand_a": "25000.00",
                },
                "indirect_costs": {
                    "indirect_cost_items": [
                        {"indirect_cost_funds_requested": "10000.00"},
                        {"indirect_cost_funds_requested": "15000.00"},
                    ]
                },
            },
            {
                "direct_costs": {
                    "direct_cost_less_consortium_fand_a": "125000.00",
                    "consortium_fand_a": "50000.00",
                },
                "indirect_costs": {
                    "indirect_cost_items": [{"indirect_cost_funds_requested": "20000.00"}]
                },
            },
        ],
        "cumulative_budget_information": {},
    }
    application_form = SimpleNamespace(
        application_response=data,
        application_form_id=uuid.uuid4(),
        form_id=uuid.uuid4(),
        form=SimpleNamespace(form_rule_schema=projected.form_rule_schema),
    )
    context = JsonRuleContext(
        application_form,
        JsonRuleConfig(do_field_validation=False),
    )

    process_rule_schema_for_context(context)

    assert [
        period["total_direct_and_indirect_costs"] for period in context.json_data["periods"]
    ] == [
        "150000.00",
        "195000.00",
    ]
    assert context.json_data["cumulative_budget_information"] == {
        "cumulative_consortium_fand_a": "75000.00",
        "cumulative_direct_cost_less_consortium_fand_a": "225000.00",
        "cumulative_total_direct_costs": "300000.00",
        "cumulative_total_indirect_costs": "45000.00",
        "cumulative_total_direct_and_indirect_costs": "345000.00",
    }

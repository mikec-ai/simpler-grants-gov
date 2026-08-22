"""R&R Subaward Budget 30 must remain a source-bound capacity profile."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms.rr_subaward_budget import RRSubawardBudget_v3_0
from src.form_schema.forms.rr_subaward_budget30 import RRSubawardBudget30_v3_0
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context

ARTIFACTS = Path("src/form_schema/form_spec/artifacts/forms/rr-subaward-budget-30")


def _without_identity_and_descriptions(value: object, *, root: bool = True) -> object:
    if isinstance(value, dict):
        return {
            key: _without_identity_and_descriptions(child, root=False)
            for key, child in value.items()
            if key != "description" and not (root and key == "$id")
        }
    if isinstance(value, list):
        return [_without_identity_and_descriptions(child, root=False) for child in value]
    return value


def test_runtime_identity_and_capacity_come_from_portable_manifest() -> None:
    loaded = load_form("rr-subaward-budget-30")

    assert loaded.meta["id"] == "rr-subaward-budget-30"
    assert loaded.meta["legacyFormId"] == 782
    assert loaded.meta["shortFormName"] == "RR_SubawardBudget30_3_0"
    assert RRSubawardBudget30_v3_0.form_type is FormType.RR_SUBAWARD_BUDGET_30
    assert (
        RRSubawardBudget30_v3_0.form_json_schema["properties"]["budget_attachments"]["maxItems"]
        == 30
    )


def test_runtime_profiles_share_schema_ui_and_rules_except_capacity_copy() -> None:
    ten_subawards = _without_identity_and_descriptions(
        copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema)
    )
    thirty_subawards = _without_identity_and_descriptions(
        copy.deepcopy(RRSubawardBudget30_v3_0.form_json_schema)
    )
    assert isinstance(ten_subawards, dict)
    assert isinstance(thirty_subawards, dict)
    thirty_subawards["properties"]["budget_attachments"]["maxItems"] = 10

    assert thirty_subawards == ten_subawards
    assert _without_identity_and_descriptions(
        RRSubawardBudget30_v3_0.form_ui_schema
    ) == _without_identity_and_descriptions(RRSubawardBudget_v3_0.form_ui_schema)
    assert RRSubawardBudget30_v3_0.form_rule_schema == RRSubawardBudget_v3_0.form_rule_schema


def test_nested_calculations_execute_independently_for_each_subaward() -> None:
    application_form = SimpleNamespace(
        application_response={
            "budget_attachments": [
                {
                    "budget_year": [
                        {"travel": {"domestic_travel_cost": "10.00"}},
                        {"travel": {"domestic_travel_cost": "15.25"}},
                    ],
                    "budget_summary": {},
                },
                {
                    "budget_year": [{"travel": {"domestic_travel_cost": "100.00"}}],
                    "budget_summary": {},
                },
            ]
        },
        form=RRSubawardBudget30_v3_0,
        application_form_id="portable-rr-subaward-budget-30-test",
        form_id=RRSubawardBudget30_v3_0.form_id,
    )
    context = JsonRuleContext(
        cast(Any, application_form),
        JsonRuleConfig(
            do_pre_population=True,
            do_post_population=False,
            do_field_validation=False,
        ),
    )

    process_rule_schema_for_context(context)

    budgets = context.json_data["budget_attachments"]
    assert [budget["budget_summary"]["cumulative_domestic_travel_costs"] for budget in budgets] == [
        "25.25",
        "100.00",
    ]


def test_wrapper_and_embedded_budget_provenance_are_pinned() -> None:
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text())

    assert [(source["type"], source["sha256"]) for source in evidence["sources"]] == [
        ("xsd", "d5d534326e8f7e4416baf98c95c1f9234c0a23628259ee2d7e3199181a24e08a"),
        ("xsd", "d474010f85819549990de65fc51292bed08ba98ac0895d0dde9513fbe855cdbc"),
    ]
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}

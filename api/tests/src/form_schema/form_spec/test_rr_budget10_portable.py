"""R&R Budget 10YR must remain a source-bound derivative of R&R Budget."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms.rr_budget import RRBudget_v3_0
from src.form_schema.forms.rr_budget10 import RRBudget10_v3_0
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context

ARTIFACTS = Path("src/form_schema/form_spec/artifacts/forms/rr-budget-10yr")


def _runtime_schema(value: object, *, root: bool = True) -> object:
    if isinstance(value, dict):
        return {
            key: _runtime_schema(child, root=False)
            for key, child in value.items()
            if not (root and key in {"$id", "description"})
            and not (root is False and key == "description")
        }
    if isinstance(value, list):
        return [_runtime_schema(child, root=False) for child in value]
    return value


def _without_descriptions(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_descriptions(child)
            for key, child in value.items()
            if key != "description"
        }
    if isinstance(value, list):
        return [_without_descriptions(child) for child in value]
    return value


def test_runtime_identity_and_period_capacity_come_from_portable_manifest() -> None:
    loaded = load_form("rr-budget-10yr")

    assert loaded.meta["id"] == "rr-budget-10yr"
    assert loaded.meta["shortFormName"] == "RR_Budget10_3_0"
    assert "legacyFormId" not in loaded.meta
    assert RRBudget10_v3_0.form_type is FormType.RR_BUDGET_10
    assert RRBudget10_v3_0.form_json_schema["properties"]["budget_year"]["maxItems"] == 10


def test_runtime_profiles_share_schema_ui_and_rules_except_period_capacity() -> None:
    five_year = _runtime_schema(copy.deepcopy(RRBudget_v3_0.form_json_schema))
    ten_year = _runtime_schema(copy.deepcopy(RRBudget10_v3_0.form_json_schema))
    assert isinstance(five_year, dict)
    assert isinstance(ten_year, dict)
    ten_year["properties"]["budget_year"]["maxItems"] = 5

    assert ten_year == five_year
    assert _without_descriptions(RRBudget10_v3_0.form_ui_schema) == _without_descriptions(
        RRBudget_v3_0.form_ui_schema
    )
    assert RRBudget10_v3_0.form_rule_schema == RRBudget_v3_0.form_rule_schema


def test_ten_year_profile_executes_the_complete_shared_calculation_graph() -> None:
    application_form = SimpleNamespace(
        application_response={
            "budget_year": [
                {"travel": {"domestic_travel_cost": "10.00"}},
                {"travel": {"domestic_travel_cost": "15.25"}},
            ],
            "budget_summary": {},
        },
        form=RRBudget10_v3_0,
        application_form_id="portable-rr-budget-10yr-test",
        form_id=RRBudget10_v3_0.form_id,
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

    assert context.json_data["budget_summary"]["cumulative_domestic_travel_costs"] == "25.25"
    assert (
        context.json_data["budget_summary"]["cumulative_total_funds_requested_direct_costs"]
        == "25.25"
    )
    assert context.json_data["budget_summary"]["cumulative_total_costs_fee"] == "25.25"


def test_official_xsd_and_extraction_provenance_are_pinned() -> None:
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text())

    assert evidence["sources"] == [
        {
            "id": "grantsgov-rr-budget-10yr-xsd-3.0",
            "type": "xsd",
            "uri": "https://apply07.grants.gov/apply/forms/schemas/RR_Budget10_3_0-V3.0.xsd",
            "nativeVersion": "3.0",
            "sha256": "e9d004c15ffcbae04b65087cb0eff7e87b8eb8ba0ffd6bfb6aba5542e04708cc",
        },
        {
            "id": "grantsgov-rr-budget-dat-3.0-f770",
            "type": "dat",
            "uri": "https://apply07.grants.gov/apply/forms/sample/RR_Budget_3_0-V3.0_F770.xls",
            "nativeVersion": None,
            "sha256": "c85158ce7ddcc756d6e8a55a050e00b4a95cdfc8d9a2d91b7bd94c7f8bdb1035",
        },
    ]
    assert evidence["extraction"]["revision"] == ("dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef")
    assert evidence["extraction"]["sourceSetSha256"] == (
        "cccce03554424d59b5958e4443a54db12a5a10780fbdc5df2ec25955d443fc9d"
    )
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}

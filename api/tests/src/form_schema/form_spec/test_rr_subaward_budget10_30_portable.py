"""The 10-year / 30-subaward profile must consume the complete shared budget behavior graph."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms.rr_subaward_budget10_30 import RRSubawardBudget10_30_v3_0
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context

ARTIFACTS = Path("src/form_schema/form_spec/artifacts/forms/rr-subaward-budget-10yr-30")


def _objects(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for child in value for item in _objects(child)]
    if not isinstance(value, dict):
        return []
    return [value, *[item for child in value.values() for item in _objects(child)]]


def test_runtime_identity_and_both_capacities_come_from_portable_manifest() -> None:
    loaded = load_form("rr-subaward-budget-10yr-30")

    assert loaded.meta["legacyFormId"] == 780
    assert loaded.meta["shortFormName"] == "RR_SubawardBudget10_30_3_0"
    assert RRSubawardBudget10_30_v3_0.form_type is FormType.RR_SUBAWARD_BUDGET_10_30
    schema = resolve_jsonschema(copy.deepcopy(RRSubawardBudget10_30_v3_0.form_json_schema))
    budgets = schema["properties"]["budget_attachments"]
    assert budgets["maxItems"] == 30
    assert budgets["items"]["properties"]["budget_year"]["maxItems"] == 10


def test_profile_requires_no_new_renderer_or_rule_capability() -> None:
    assert (
        len(
            [
                node
                for node in _objects(RRSubawardBudget10_30_v3_0.form_ui_schema)
                if node.get("type") == "fieldList"
            ]
        )
        == 6
    )
    assert (
        len(
            [
                node
                for node in _objects(RRSubawardBudget10_30_v3_0.form_rule_schema)
                if "gg_pre_population" in node
            ]
        )
        == 56
    )
    assert "@PARENT." in json.dumps(RRSubawardBudget10_30_v3_0.form_rule_schema)


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
        form=RRSubawardBudget10_30_v3_0,
        application_form_id="portable-rr-subaward-budget-10yr-30-test",
        form_id=RRSubawardBudget10_30_v3_0.form_id,
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


def test_wrapper_and_dependency_provenance_are_pinned_and_unreviewed() -> None:
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text())

    assert {source["sha256"] for source in evidence["sources"]} == {
        "e9d004c15ffcbae04b65087cb0eff7e87b8eb8ba0ffd6bfb6aba5542e04708cc",
        "0ed112b2e50f0e0c43423f690201b207f5b9c5a85349335260e4fd999f3a611a",
        "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
        "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
        "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
        "c85158ce7ddcc756d6e8a55a050e00b4a95cdfc8d9a2d91b7bd94c7f8bdb1035",
    }
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}

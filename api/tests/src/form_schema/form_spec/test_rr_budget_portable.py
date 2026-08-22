"""R&R Budget 3.0 must remain a source-bound portable form package."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from jsonschema import Draft202012Validator

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms.rr_budget import RRBudget_v3_0
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from tests.src.form_schema.form_spec.parity import pointers, rendered_field

ARTIFACTS = Path("src/form_schema/form_spec/artifacts/forms/rr-budget")


def _objects(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        return [node, *[item for value in node.values() for item in _objects(value)]]
    if isinstance(node, list):
        return [item for value in node for item in _objects(value)]
    return []


def test_runtime_identity_comes_from_the_portable_manifest() -> None:
    loaded = load_form("rr-budget")

    assert loaded.meta == {
        "id": "rr-budget",
        "formId": "cfa593f7-e5ef-4ba8-82b2-c732ec65e461",
        "legacyFormId": 770,
        "formName": "[Draft] Research & Related Budget",
        "shortFormName": "RR_Budget_3_0",
        "formVersion": "3.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
        "formType": "RRBudget",
        "sggVersion": "1.0",
    }
    assert RRBudget_v3_0.form_type is FormType.RR_BUDGET
    assert resolve_jsonschema(copy.deepcopy(RRBudget_v3_0.form_json_schema)) == resolve_jsonschema(
        copy.deepcopy(loaded.form_json_schema)
    )
    assert cast(Any, RRBudget_v3_0.form_ui_schema) == loaded.form_ui_schema
    assert RRBudget_v3_0.form_rule_schema == loaded.form_rule_schema


def test_every_rendered_pointer_resolves_through_the_shared_bank() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRBudget_v3_0.form_json_schema))
    ui_pointers = pointers(RRBudget_v3_0.form_ui_schema)

    assert len(ui_pointers) == 162
    assert len(set(ui_pointers)) == len(ui_pointers)
    assert all(rendered_field(schema, pointer) is not None for pointer in ui_pointers)


def test_repeating_groups_and_rules_are_projected_without_form_code() -> None:
    ui_objects = _objects(RRBudget_v3_0.form_ui_schema)
    rule_objects = _objects(RRBudget_v3_0.form_rule_schema)
    calculations = [
        node["gg_pre_population"] for node in rule_objects if "gg_pre_population" in node
    ]
    attachments = [node["gg_validation"] for node in rule_objects if "gg_validation" in node]

    assert sum(node.get("type") == "fieldList" for node in ui_objects) == 5
    assert len(calculations) == 56
    assert sorted(rule["order"] for rule in calculations) == list(range(1, 57))
    assert sum(rule["rule"] == "sum_integer" for rule in calculations) == 3
    assert len(attachments) == 3


def test_decimal_wire_constraints_are_preserved() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRBudget_v3_0.form_json_schema))
    schema_objects = _objects(schema)
    assert sum("pattern" in node for node in schema_objects) == 115

    fee = schema["properties"]["budget_year"]["items"]["properties"]["fee"]
    validator = Draft202012Validator(fee)
    for value in ("0", "12345678901234", "123456789012.34"):
        assert list(validator.iter_errors(value)) == []
    invalid_values: tuple[Any, ...] = (1.2, "-1.2", "1234567890123.45", "1.234")
    for value in invalid_values:
        assert list(validator.iter_errors(value))


def test_source_resolved_calculations_execute_in_declared_order() -> None:
    application_form = SimpleNamespace(
        application_response={
            "budget_year": [
                {
                    "key_persons": {
                        "key_person": [
                            {"requested_salary": "100.00", "fringe_benefits": "20.00"},
                            {"requested_salary": "75.50", "fringe_benefits": "4.50"},
                        ]
                    },
                    "other_personnel": {
                        "post_doc_associates": {"number_of_personnel": 2},
                        "other": [{"number_of_personnel": 3}],
                    },
                    "travel": {"domestic_travel_cost": "10.00"},
                },
                {"travel": {"domestic_travel_cost": "15.25"}},
            ],
            "budget_summary": {},
        },
        form=RRBudget_v3_0,
        application_form_id="portable-form-test",
        form_id=RRBudget_v3_0.form_id,
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

    people = context.json_data["budget_year"][0]["key_persons"]["key_person"]
    assert [person["funds_requested"] for person in people] == ["120.00", "80.00"]
    assert context.json_data["budget_year"][0]["key_persons"]["total_fund_for_key_persons"] == "200.00"
    assert context.json_data["budget_year"][0]["other_personnel"]["other_personnel_total_number"] == 5
    assert context.json_data["budget_year"][0]["direct_costs"] == "210.00"
    assert context.json_data["budget_year"][0]["total_costs_fee"] == "210.00"
    assert context.json_data["budget_summary"]["cumulative_domestic_travel_costs"] == "25.25"
    assert context.json_data["budget_summary"]["cumulative_total_funds_requested_direct_costs"] == "225.25"
    assert context.json_data["budget_summary"]["cumulative_total_costs_fee"] == "225.25"


def test_official_source_and_extraction_provenance_are_pinned() -> None:
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text())

    assert evidence["sources"] == [
        {
            "id": "grantsgov-rr-budget-xsd-3.0",
            "type": "xsd",
            "uri": "https://apply07.grants.gov/apply/forms/schemas/RR_Budget_3_0-V3.0.xsd",
            "version": "3.0",
            "sha256": "d474010f85819549990de65fc51292bed08ba98ac0895d0dde9513fbe855cdbc",
        },
        {
            "id": "grantsgov-rr-budget-dat-3.0-f770",
            "type": "dat",
            "uri": "https://apply07.grants.gov/apply/forms/sample/RR_Budget_3_0-V3.0_F770.xls",
            "version": "3.0",
            "sha256": "c85158ce7ddcc756d6e8a55a050e00b4a95cdfc8d9a2d91b7bd94c7f8bdb1035",
        },
    ]
    assert evidence["extraction"]["revision"] == "dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef"
    assert (
        evidence["extraction"]["sourceSetSha256"]
        == "b318951e0686bd7978ab791bd63ad36d6fa6e93b6368747b272526360e99fedb"
    )
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}

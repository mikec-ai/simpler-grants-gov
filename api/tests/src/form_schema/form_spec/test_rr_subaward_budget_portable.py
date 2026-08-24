"""R&R Subaward Budget 3.0 must remain a source-bound portable form package."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from jsonschema import Draft202012Validator

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms.rr_subaward_budget import RRSubawardBudget_v3_0
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from tests.src.form_schema.form_spec.parity import pointers, rendered_field

ARTIFACTS = Path("src/form_schema/form_spec/artifacts/forms/rr-subaward-budget")


def _objects(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        return [node, *[item for value in node.values() for item in _objects(value)]]
    if isinstance(node, list):
        return [item for value in node for item in _objects(value)]
    return []


def test_portable_metadata_and_sgg_runtime_identity_stay_separate() -> None:
    loaded = load_form("rr-subaward-budget")

    assert loaded.meta == {
        "id": "rr-subaward-budget",
        "legacyFormId": 776,
        "formName": "[Draft] R&R Subaward Budget Attachment(s) Form",
        "shortFormName": "RR_SubawardBudget_3_0",
        "formVersion": "3.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
    }
    assert str(RRSubawardBudget_v3_0.form_id) == "67450974-a273-5bb8-86e5-b88d8a68c732"
    assert RRSubawardBudget_v3_0.form_type is FormType.RR_SUBAWARD_BUDGET
    assert RRSubawardBudget_v3_0.sgg_version == "1.0"
    assert resolve_jsonschema(
        copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema)
    ) == resolve_jsonschema(copy.deepcopy(loaded.form_json_schema))
    assert cast(Any, RRSubawardBudget_v3_0.form_ui_schema) == loaded.form_ui_schema
    assert RRSubawardBudget_v3_0.form_rule_schema == loaded.form_rule_schema


def test_every_rendered_pointer_resolves_through_the_shared_bank() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema))
    ui_pointers = pointers(RRSubawardBudget_v3_0.form_ui_schema)

    assert len(ui_pointers) == 163
    assert len(set(ui_pointers)) == len(ui_pointers)
    assert all(rendered_field(schema, pointer) is not None for pointer in ui_pointers)


def test_nested_repeating_groups_and_rules_are_projected_generically() -> None:
    ui_objects = _objects(RRSubawardBudget_v3_0.form_ui_schema)
    rule_objects = _objects(RRSubawardBudget_v3_0.form_rule_schema)
    calculations = [
        node["gg_pre_population"] for node in rule_objects if "gg_pre_population" in node
    ]

    assert sum(node.get("type") == "fieldList" for node in ui_objects) == 6
    assert len(calculations) == 56
    assert sum(rule.get("materialize") == "when_any_source_present" for rule in calculations) == 20
    raw_rules = json.loads((ARTIFACTS / "sgg" / "rule-schema.json").read_text())
    assert "@PARENT." in json.dumps(raw_rules)
    assert "@PARENT." in json.dumps(RRSubawardBudget_v3_0.form_rule_schema)
    assert sorted(rule["order"] for rule in calculations) == list(range(1, 57))
    assert sum(rule["rule"] == "sum_integer" for rule in calculations) == 3


def test_nested_cross_section_condition_projects_without_an_adapter_branch() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema))
    budget_period = schema["properties"]["budget_attachments"]["items"]["properties"][
        "budget_year"
    ]["items"]
    [condition] = budget_period["allOf"]
    validator = Draft202012Validator(condition)

    assert list(validator.iter_errors({})) == []
    triggered = {
        "participant_trainee_support_costs": {
            "other": {"cost": "1.00", "description": "Participant support"}
        }
    }
    assert list(validator.iter_errors(triggered))
    assert list(
        validator.iter_errors(
            {
                **triggered,
                "other_direct_costs": {"other_direct_cost10": {}},
            }
        )
    )
    assert (
        list(
            validator.iter_errors(
                {
                    **triggered,
                    "other_direct_costs": {
                        "other_direct_cost10": {"description": "Non-sequential row"}
                    },
                }
            )
        )
        == []
    )


def test_nested_positive_attachment_totals_validate_without_an_adapter_branch() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema))
    period_properties = schema["properties"]["budget_attachments"]["items"]["properties"][
        "budget_year"
    ]["items"]["properties"]
    pairs = (
        (
            period_properties["equipment"],
            "additional_equipments_attachment",
            "total_fund_for_attached_equipment",
        ),
        (
            period_properties["key_persons"],
            "attached_key_persons",
            "total_fund_for_attached_key_persons",
        ),
    )

    for group, attachment, total in pairs:
        validator = Draft202012Validator({"allOf": group["allOf"]})
        assert list(validator.iter_errors({})) == []
        assert list(validator.iter_errors({total: "0.00"})) == []
        assert list(validator.iter_errors({total: "1.00"}))
        assert list(validator.iter_errors({attachment: "file-id"}))
        assert list(validator.iter_errors({attachment: "file-id", total: "0.00"}))
        assert list(validator.iter_errors({attachment: "file-id", total: "0.01"})) == []


def test_nested_cumulative_calculations_resolve_within_each_subaward() -> None:
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
        form=RRSubawardBudget_v3_0,
        application_form_id="portable-rr-subaward-budget-test",
        form_id=RRSubawardBudget_v3_0.form_id,
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


def test_nested_source_conditioned_calculation_distinguishes_absence_from_zero() -> None:
    application_form = SimpleNamespace(
        application_response={
            "budget_attachments": [
                {
                    "budget_year": [{"travel": {"total_travel_cost": "99.00"}}],
                    "budget_summary": {},
                },
                {
                    "budget_year": [{"travel": {"domestic_travel_cost": "0.00"}}],
                    "budget_summary": {},
                },
            ]
        },
        form=RRSubawardBudget_v3_0,
        application_form_id="portable-subaward-materialization-test",
        form_id=RRSubawardBudget_v3_0.form_id,
    )
    context = JsonRuleContext(
        cast(Any, application_form), JsonRuleConfig(do_field_validation=False)
    )

    process_rule_schema_for_context(context)

    budgets = context.json_data["budget_attachments"]
    first_travel = budgets[0]["budget_year"][0]["travel"]
    second_travel = budgets[1]["budget_year"][0]["travel"]
    assert "total_travel_cost" not in first_travel
    assert second_travel["total_travel_cost"] == "0.00"


def test_nested_cumulative_other_personnel_presence_follows_entered_sources() -> None:
    application_form = SimpleNamespace(
        application_response={
            "budget_attachments": [
                {"budget_year": [{"other_personnel": {}}], "budget_summary": {}},
                {
                    "budget_year": [
                        {
                            "other_personnel": {
                                "post_doc_associates": {
                                    "requested_salary": "0.00",
                                    "number_of_personnel": 0,
                                }
                            }
                        }
                    ],
                    "budget_summary": {},
                },
            ]
        },
        form=RRSubawardBudget_v3_0,
        application_form_id="portable-subaward-transitive-presence-test",
        form_id=RRSubawardBudget_v3_0.form_id,
    )
    context = JsonRuleContext(
        cast(Any, application_form), JsonRuleConfig(do_field_validation=False)
    )

    process_rule_schema_for_context(context)

    absent, explicit_zero = [
        budget["budget_summary"] for budget in context.json_data["budget_attachments"]
    ]
    assert "cumulative_total_funds_requested_other_personnel" not in absent
    assert "cumulative_total_no_other_personnel" not in absent
    assert explicit_zero["cumulative_total_funds_requested_other_personnel"] == "0.00"
    assert explicit_zero["cumulative_total_no_other_personnel"] == 0


def test_official_xsd_and_dat_provenance_are_pinned() -> None:
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text())

    assert [(source["type"], source["sha256"]) for source in evidence["sources"]] == [
        ("xsd", "e1ea95403a58ef1ade290952de3531c73e015308ca7aee6b426d4a9bcb794510"),
        ("dat", "4eab979aa62d4a4e79da6ee536140da7b76545a8fc20a9897c1c13527b3c56fd"),
        ("dat", "c85158ce7ddcc756d6e8a55a050e00b4a95cdfc8d9a2d91b7bd94c7f8bdb1035"),
    ]
    assert len(evidence["behaviorEvidence"]) == 70
    assert (
        sum(record["authority"] == "official_source" for record in evidence["behaviorEvidence"])
        == 34
    )
    assert sum(record["authority"] == "unresolved" for record in evidence["behaviorEvidence"]) == 36
    assert {
        (record["sourceId"], record["inheritedFrom"])
        for record in evidence["behaviorEvidence"]
        if record["authority"] == "official_source"
    } == {("grantsgov-rr-budget-dat-3.0-f770", "rr-budget")}
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    conditions = [
        record for record in evidence["behaviorEvidence"] if record["ruleKind"] == "condition"
    ]
    assert len(conditions) == 14
    assert {record["sourcePath"] for record in conditions} == {
        "F-8-1",
        "A-2-1",
        "A-3-1",
        "C-2-0",
        "C-2-1",
    }
    assert {record["executionStatus"] for record in conditions} == {"compiled"}

"""SF-424C proves the supervised producer-to-consumer promotion path."""

from __future__ import annotations

import copy
import json
import re
import uuid
from types import SimpleNamespace

from src.form_schema.form_spec.bank import ARTIFACTS, verify_artifacts
from src.form_schema.form_spec.loader import build_runtime_form, load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.forms.sf424c import SF424c_v2_0
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context

INPUT_ROWS = (
    "administrative_and_legal_expenses",
    "land_structures_rights_of_way",
    "relocation_expenses",
    "architectural_engineering_fees",
    "other_architectural_engineering_fees",
    "project_inspection_fees",
    "site_work",
    "demolition_and_removal",
    "construction",
    "equipment",
    "miscellaneous",
)


def calculated_response() -> dict:
    """Run all 24 portable calculations against the legacy-compatible response shape."""

    row = {"total_cost": "100000.00", "non_allowable_cost": "10000.00"}
    data = {
        "budget_information": {name: dict(row) for name in INPUT_ROWS},
        "federal_funding": {"federal_percentage_share": 80},
    }
    data["budget_information"].update(
        {
            "contingencies": {"total_cost": "55000.00", "non_allowable_cost": "5000.00"},
            "project_income": {"total_cost": "10000.00", "non_allowable_cost": "0.00"},
        }
    )
    projected = load_form("sf424c")
    application_form = SimpleNamespace(
        application_response=data,
        application_form_id=uuid.uuid4(),
        form_id=uuid.uuid4(),
        form=SimpleNamespace(form_rule_schema=projected.form_rule_schema),
    )
    context = JsonRuleContext(application_form, JsonRuleConfig(do_field_validation=False))
    process_rule_schema_for_context(context)
    return context.json_data


def test_promoted_form_preserves_legacy_runtime_and_response_identity() -> None:
    portable = load_form("sf424c")
    runtime = build_runtime_form("sf424c")
    portable_schema = resolve_jsonschema(copy.deepcopy(portable.form_json_schema))
    oracle_schema = resolve_jsonschema(copy.deepcopy(SF424c_v2_0.form_json_schema))

    assert portable.meta == {
        "id": "sf424c",
        "legacyFormId": 408,
        "formName": "Budget Information for Construction Programs (SF-424C)",
        "shortFormName": "SF424C",
        "formVersion": "2.0",
        "agencyCode": "SGG",
        "ombNumber": "4040-0008",
    }
    assert runtime.form_id == SF424c_v2_0.form_id
    assert runtime.form_type == SF424c_v2_0.form_type
    assert runtime.sgg_version == SF424c_v2_0.sgg_version
    assert set(portable_schema["properties"]) == set(oracle_schema["properties"])
    assert set(portable_schema["properties"]["budget_information"]["properties"]) == set(
        oracle_schema["properties"]["budget_information"]["properties"]
    )
    assert set(portable_schema["properties"]["federal_funding"]["properties"]) == set(
        oracle_schema["properties"]["federal_funding"]["properties"]
    )


def test_all_calculations_execute_with_source_aware_materialization() -> None:
    response = calculated_response()
    budget = response["budget_information"]

    assert all(budget[name]["total_allowable_cost"] == "90000.00" for name in INPUT_ROWS)
    assert budget["subtotal_1"] == {
        "total_cost": "1100000.00",
        "non_allowable_cost": "110000.00",
        "total_allowable_cost": "990000.00",
    }
    assert budget["subtotal_2"] == {
        "total_cost": "1155000.00",
        "non_allowable_cost": "115000.00",
        "total_allowable_cost": "1040000.00",
    }
    assert budget["total_project_costs"] == {
        "total_cost": "1145000.00",
        "non_allowable_cost": "115000.00",
        "total_allowable_cost": "1030000.00",
    }
    assert response["federal_funding"] == {
        "federal_percentage_share": 80,
        "total_project_costs": "1030000.00",
        "federal_funding_share": "824000.00",
    }


def test_table_layout_projects_all_rows_and_cell_paths_generically() -> None:
    table = load_form("sf424c").form_ui_schema[0]["children"][0]

    assert table["widget"] == "Table"
    assert table["definition"] == ["/properties/budget_information"]
    assert [column["columnHeader"] for column in table["children"]["columns"]] == [
        "Cost Classification",
        "Total Cost",
        "Costs Not Allowable for Participation",
        "Total Allowable Costs (Columns a - b)",
    ]
    rows = table["children"]["rows"]
    assert len(rows) == 16
    assert all(len(row["cells"]) == 4 for row in rows)
    assert rows[0]["cells"][1:] == [
        {
            "type": "input",
            "definition": "/properties/administrative_and_legal_expenses/properties/total_cost",
            "format": "dollar",
        },
        {
            "type": "input",
            "definition": (
                "/properties/administrative_and_legal_expenses/properties/non_allowable_cost"
            ),
            "format": "dollar",
        },
        {
            "type": "readOnly",
            "definition": (
                "/properties/administrative_and_legal_expenses/properties/total_allowable_cost"
            ),
            "format": "dollar",
        },
    ]
    assert all(cell["type"] == "readOnly" for cell in rows[-1]["cells"][1:])


def test_promotion_receipt_boundary_and_release_gates_remain_explicit() -> None:
    manifest = verify_artifacts()
    evidence = json.loads((ARTIFACTS / "forms/sf424c/evidence.json").read_text())
    registrations = json.loads(REGISTRATIONS.read_text())["forms"]

    assert re.fullmatch(r"[0-9a-f]{40}", manifest["source"]["revision"])
    assert "sf424c" in manifest["selection"]["forms"]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 18
    assert "sf424c" not in registrations

"""PHS Additional Indirect Costs portable handoff evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form
from src.form_schema.form_spec.preview import build_preview_form
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator

FORM_ID = "phs-additional-indirect-costs"
INTRODUCED_BY_PRODUCER_REVISION = "893b0710ee69d8e3455b5c954e9071504a3a61b0"
REPAIRED_BY_PRODUCER_REVISION = "4b3b1d78a96ea8e501f51e6edbaa0190d67b9949"
EMITTED_FROM_PRODUCER_REVISION = REPAIRED_BY_PRODUCER_REVISION
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
XSD_NAME = "PHS_Additional_IndirectCosts_2_0-V2.0.xsd"
XSD_SHA256 = "ba38a3500b025b0414edbcdbffe80dc12165ceb7a7fb657012d450b2e9682b66"
PRODUCER_REPAIR_FORM_ARTIFACT_SHA256 = {
    "evidence.json": "d9090065ce7934918362241006f89214e357898320865d1de3b93e5079c66999",
    "manifest.json": "cd9dd69252fc7083ee3a8f2a5adf75c3de2806bf1a3a7a906f5b39ae7d70b585",
    "schema.json": "c000d65146d11b55d25ca2d5d3a75fc8206ed3b9310e1f419596484f5ecebe29",
    "sgg/rule-schema.json": ("6c295acf7f2a71b2db23b010442e7fc4bf04b3ce1f953f4c172c5afab026093b"),
    "sgg/ui-schema.json": ("b5310ed607acf851c740ffb684915a51773bba8e33d26c15186e811a0d21ba5a"),
    "targets/grants-gov-xml.json": (
        "f50ca62f30f5c52fae4efc1e744248bd8b70094c0b9baa3428719239e1bcff46"
    ),
}
PRODUCER_REPAIR_PERIOD_SCHEMA_SHA256 = (
    "0b07fd91c3b71121f95bef32f98737d190b804d9be11a479de8de708766dfd1d"
)


def _representative_response() -> dict:
    return {
        "budget_years": [
            {
                "sam_uei": "ABCDEFGHIJKL",
                "organization_name": "Example Organization",
                "budget_type": "Project",
                "budget_period_start_date": "2026-01-01",
                "budget_period_end_date": "2026-12-31",
                "indirect_costs": {
                    "indirect_cost": [
                        {
                            "cost_type": "MTDC",
                            "rate": "10.00",
                            "base": "1000.00",
                            "fund_requested": "100.00",
                        },
                        {"cost_type": "Other", "fund_requested": "25.00"},
                    ]
                },
            },
            {
                "budget_period_start_date": "2027-01-01",
                "budget_period_end_date": "2027-12-31",
                "indirect_costs": {
                    "indirect_cost": [{"cost_type": "MTDC", "fund_requested": "200.00"}]
                },
            },
        ],
        "budget_summary": {},
    }


def _apply_rules(response: dict) -> dict:
    projected = _load_banked_form(FORM_ID)
    application_form = cast(
        ApplicationForm,
        SimpleNamespace(
            application_response=response,
            application_form_id=uuid.uuid4(),
            form_id=uuid.uuid4(),
            form=SimpleNamespace(form_rule_schema=projected.form_rule_schema),
        ),
    )
    context = JsonRuleContext(application_form, JsonRuleConfig(do_field_validation=False))
    process_rule_schema_for_context(context)
    return context.json_data


def _calculated_response() -> dict:
    return _apply_rules(_representative_response())


def _xml(response: dict) -> str:
    projected = _load_banked_form(FORM_ID)
    assert projected.json_to_xml_schema is not None
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=projected.json_to_xml_schema,
            attachment_mapping={},
        )
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    return generated.xml_data


def test_preview_uses_generic_nested_budget_controls() -> None:
    form = build_preview_form(FORM_ID)

    assert form.form_name == "[Portable preview] PHS Additional Indirect Costs"
    assert form.form_version == "2.0"
    assert form.legacy_form_id == 739
    assert form.form_json_schema["properties"]["budget_years"]["maxItems"] == 10
    period = form.form_json_schema["properties"]["budget_years"]["items"]
    indirect_costs = period["properties"]["indirect_costs"]
    rows = indirect_costs["properties"]["indirect_cost"]
    assert rows["maxItems"] == 4
    assert rows["items"]["properties"]["cost_type"]["minLength"] == 1
    assert _load_banked_form(FORM_ID).json_to_xml_schema is not None


def test_exact_dat_backed_calculations_execute_through_generic_rules() -> None:
    response = _calculated_response()

    assert [
        period["indirect_costs"]["total_indirect_costs"] for period in response["budget_years"]
    ] == ["125.00", "200.00"]
    assert response["budget_summary"]["cumulative_total_funds_requested_indirect_cost"] == (
        "325.00"
    )


def test_dates_only_period_does_not_materialize_optional_cost_or_summary_branches() -> None:
    response = _apply_rules(
        {
            "budget_years": [
                {
                    "budget_period_start_date": "2026-01-01",
                    "budget_period_end_date": "2026-12-31",
                }
            ]
        }
    )

    assert "indirect_costs" not in response["budget_years"][0]
    assert "budget_summary" not in response


def test_cumulative_total_depends_only_on_materialized_period_totals() -> None:
    response = _apply_rules(
        {
            "budget_years": [
                {
                    "budget_period_start_date": "2026-01-01",
                    "budget_period_end_date": "2026-12-31",
                    "indirect_costs": {
                        "indirect_cost": [{"cost_type": "MTDC", "fund_requested": "100.00"}]
                    },
                },
                {
                    "budget_period_start_date": "2027-01-01",
                    "budget_period_end_date": "2027-12-31",
                },
            ]
        }
    )

    assert response["budget_years"][0]["indirect_costs"]["total_indirect_costs"] == ("100.00")
    assert "indirect_costs" not in response["budget_years"][1]
    assert response["budget_summary"] == {
        "cumulative_total_funds_requested_indirect_cost": "100.00"
    }


def test_generated_xml_validates_against_exact_official_xsd() -> None:
    xsd = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == XSD_SHA256
    result = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        _xml(_calculated_response()), XSD_NAME.removesuffix(".xsd")
    )

    assert result["valid"], result


def test_source_and_review_gates_remain_explicit() -> None:
    root = ARTIFACTS / "forms" / FORM_ID
    evidence = json.loads((root / "evidence.json").read_text())

    assert evidence["extraction"] == {
        "artifact": (
            "artifacts/authoring/fed-nonfed-budget-family/forms/PHSAdditionalIndirectCosts.json"
        ),
        "extractedAt": "2026-08-19T23:33:45Z",
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef",
        "sourceSetSha256": ("991e5e4d3e8f0cff585bf8d5dc59e59e6b3225b2132fc8bafdd54d7b4d74ae65"),
    }
    assert evidence["semanticReview"] == {"mappings": [], "status": "unreviewed"}
    assert {
        (item["canonicalPath"], item["executionStatus"]) for item in evidence["behaviorEvidence"]
    } == {
        ("budgetYears[*].indirectCosts.totalIndirectCosts", "compiled"),
        ("budgetSummary.cumulativeTotalFundsRequestedIndirectCost", "compiled"),
    }
    assert {source["type"] for source in evidence["sources"]} == {"dat", "xsd"}


def test_current_pin_preserves_producer_repair_receipts() -> None:
    root = ARTIFACTS / "forms" / FORM_ID
    manifest = json.loads((ARTIFACTS / "artifact-manifest.json").read_text())

    assert INTRODUCED_BY_PRODUCER_REVISION == ("893b0710ee69d8e3455b5c954e9071504a3a61b0")
    assert REPAIRED_BY_PRODUCER_REVISION == ("4b3b1d78a96ea8e501f51e6edbaa0190d67b9949")
    assert manifest["source"]["revision"] == EMITTED_FROM_PRODUCER_REVISION
    assert {
        relative_path: hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        for relative_path in PRODUCER_REPAIR_FORM_ARTIFACT_SHA256
    } == PRODUCER_REPAIR_FORM_ARTIFACT_SHA256
    period_schema = ARTIFACTS / "question-bank/budget/additional-indirect-costs/period/schema.json"
    assert hashlib.sha256(period_schema.read_bytes()).hexdigest() == (
        PRODUCER_REPAIR_PERIOD_SCHEMA_SHA256
    )

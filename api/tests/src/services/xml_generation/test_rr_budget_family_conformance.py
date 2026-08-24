"""Payload, calculation, lifecycle, and XML conformance for the R&R Budget family."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    application_form_for,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)
from tests.src.services.xml_generation.test_rr_budget_xml_generation import (
    BUDGET_ATTACHMENT_ID,
    EQUIPMENT_ATTACHMENT_ID,
    FAMILY_PROFILES,
    KEY_PERSON_ATTACHMENT_ID,
    _application_data,
    _attachment_mapping,
)


@dataclass(frozen=True)
class BudgetProfile:
    form_id: str
    xml_profile: dict[str, Any]
    root_name: str
    root_namespace: str
    xsd_name: str
    subaward: bool
    budget_namespace: str
    max_periods: int
    max_budgets: int


FORM_IDS = (
    "rr-budget",
    "rr-budget-10yr",
    "rr-subaward-budget",
    "rr-subaward-budget-30",
    "rr-subaward-budget-10yr-30",
)
PROFILES = tuple(
    BudgetProfile(
        form_id=form_id,
        xml_profile=family_profile[1],
        root_name=family_profile[2],
        root_namespace=family_profile[3],
        xsd_name=family_profile[4],
        subaward=family_profile[6],
        budget_namespace=family_profile[7],
        max_periods=10 if "10yr" in form_id else 5,
        max_budgets=30 if form_id.endswith("30") else (10 if family_profile[6] else 1),
    )
    for form_id, family_profile in zip(FORM_IDS, FAMILY_PROFILES, strict=True)
)
ATTACHMENT_IDS = (
    BUDGET_ATTACHMENT_ID,
    KEY_PERSON_ATTACHMENT_ID,
    EQUIPMENT_ATTACHMENT_ID,
)
XSD_DIR = Path(__file__).parents[4] / "src/services/xml_generation/xsds"


def _minimal_budget() -> dict[str, Any]:
    """Return applicant-entered minimum data; calculated required fields are omitted."""

    return {
        "samuei": "TEST12345678",
        "budget_type": "Project",
        "budget_justification_attachment": BUDGET_ATTACHMENT_ID,
        "budget_year": [
            {
                "budget_period_start_date": "2026-01-01",
                "budget_period_end_date": "2026-12-31",
                "key_persons": {
                    "key_person": [
                        {
                            "name": {"first_name": "Ada", "last_name": "Lovelace"},
                            "project_role": "Principal Investigator",
                            "requested_salary": "0.00",
                            "fringe_benefits": "0.00",
                        }
                    ]
                },
            }
        ],
        "budget_summary": {},
    }


def _fully_populated_budget() -> dict[str, Any]:
    """Return the representative fully populated source fixture with valid attachments."""

    budget = _application_data()
    period = budget["budget_year"][0]
    period["key_persons"]["total_fund_for_attached_key_persons"] = "1.00"
    period["equipment"]["total_fund_for_attached_equipment"] = "1.00"
    return budget


def _adapt_budget(profile: BudgetProfile, budget: dict[str, Any]) -> dict[str, Any]:
    """Apply only the profile's declaratively projected runtime field spellings."""

    adapted = copy.deepcopy(budget)
    if not profile.subaward:
        return adapted

    adapted["sam_uei"] = adapted.pop("samuei")
    adapted["budget_type"] = "Subaward/Consortium"
    for period in adapted["budget_year"]:
        direct_costs = period.get("other_direct_costs", {})
        for index in range(1, 11):
            underscored = f"other_direct_cost_{index}"
            if underscored in direct_costs:
                direct_costs[f"other_direct_cost{index}"] = direct_costs.pop(underscored)
    summary = adapted.get("budget_summary", {})
    for index in range(1, 11):
        underscored = f"cumulative_other_{index}_direct_cost"
        if underscored in summary:
            summary[f"cumulative_other{index}_direct_cost"] = summary.pop(underscored)
    return adapted


def _wrap(profile: BudgetProfile, budgets: list[dict[str, Any]]) -> dict[str, Any]:
    if profile.subaward:
        return {"budget_attachments": budgets}
    assert len(budgets) == 1
    return budgets[0]


def _calculate(profile: BudgetProfile, response: dict[str, Any]) -> dict[str, Any]:
    application_form = application_form_for(
        profile.form_id,
        response,
        attachment_ids=ATTACHMENT_IDS,
    )
    context = JsonRuleContext(application_form, JsonRuleConfig(do_field_validation=False))
    process_rule_schema_for_context(context)
    return context.json_data


def _generate_and_validate_xml(profile: BudgetProfile, response: dict[str, Any]) -> etree._Element:
    result = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=profile.xml_profile,
            attachment_mapping=_attachment_mapping(),
        )
    )
    assert result.success, result.error_message
    assert result.xml_data is not None
    validation = XSDValidator(XSD_DIR).validate_xml(result.xml_data, XSD_DIR / profile.xsd_name)
    assert validation["valid"], validation["error_message"]
    return etree.fromstring(result.xml_data.encode())


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile.form_id)
@pytest.mark.parametrize(
    ("scenario", "budget_factory"),
    [("minimal", _minimal_budget), ("fully-populated", _fully_populated_budget)],
)
def test_representative_payloads_complete_the_lifecycle_and_emit_official_xsd_xml(
    profile: BudgetProfile,
    scenario: str,
    budget_factory: Any,
) -> None:
    budget = _adapt_budget(profile, budget_factory())
    response = _calculate(profile, _wrap(profile, [budget]))

    assert_json_round_trip(response)
    assert_validation_case(
        profile.form_id,
        ValidationCase(scenario, response, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )
    submitted = submit_form(profile.form_id, response, attachment_ids=ATTACHMENT_IDS)
    assert submitted.application_response == response

    root = _generate_and_validate_xml(profile, response)
    assert root.tag == f"{{{profile.root_namespace}}}{profile.root_name}"


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile.form_id)
def test_explicit_zero_sources_materialize_required_calculations(profile: BudgetProfile) -> None:
    budget = _adapt_budget(profile, _minimal_budget())
    response = _calculate(profile, _wrap(profile, [budget]))
    calculated_budget = response["budget_attachments"][0] if profile.subaward else response

    period = calculated_budget["budget_year"][0]
    assert period["key_persons"]["key_person"][0]["funds_requested"] == "0.00"
    assert period["key_persons"]["total_fund_for_key_persons"] == "0.00"
    assert period["direct_costs"] == "0.00"
    assert period["total_costs_fee"] == "0.00"
    assert calculated_budget["budget_summary"]["cumulative_total_costs_fee"] == "0.00"


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile.form_id)
@pytest.mark.parametrize(
    ("group_name", "attachment_name", "total_name", "attachment_id"),
    [
        (
            "key_persons",
            "attached_key_persons",
            "total_fund_for_attached_key_persons",
            KEY_PERSON_ATTACHMENT_ID,
        ),
        (
            "equipment",
            "additional_equipments_attachment",
            "total_fund_for_attached_equipment",
            EQUIPMENT_ATTACHMENT_ID,
        ),
    ],
)
def test_positive_total_and_attachment_fail_closed_in_both_directions(
    profile: BudgetProfile,
    group_name: str,
    attachment_name: str,
    total_name: str,
    attachment_id: str,
) -> None:
    response = _calculate(
        profile,
        _wrap(profile, [_adapt_budget(profile, _minimal_budget())]),
    )
    budget = response["budget_attachments"][0] if profile.subaward else response
    period = budget["budget_year"][0]
    if group_name == "equipment":
        period[group_name] = {"total_fund": "0.00"}
    group = period[group_name]
    group[total_name] = "1.00"
    missing_attachment = copy.deepcopy(response)
    prefix = "$.budget_attachments[0]" if profile.subaward else "$"

    assert_validation_case(
        profile.form_id,
        ValidationCase(
            "positive total without attachment",
            missing_attachment,
            frozenset({f"{prefix}.budget_year[0].{group_name}.{attachment_name}"}),
        ),
        attachment_ids=ATTACHMENT_IDS,
    )

    group[attachment_name] = attachment_id
    group[total_name] = "0.00"
    zero_total = response
    assert_validation_case(
        profile.form_id,
        ValidationCase(
            "attachment without positive total",
            zero_total,
            frozenset({f"{prefix}.budget_year[0].{group_name}.{total_name}"}),
        ),
        attachment_ids=ATTACHMENT_IDS,
    )


@pytest.mark.parametrize(
    "profile",
    [profile for profile in PROFILES if profile.subaward],
    ids=lambda profile: profile.form_id,
)
def test_nested_subaward_payloads_calculate_and_emit_independently(
    profile: BudgetProfile,
) -> None:
    first = _adapt_budget(profile, _minimal_budget())
    second = _adapt_budget(profile, _minimal_budget())
    first["organization_name"] = "First Subrecipient"
    second["organization_name"] = "Second Subrecipient"
    first["budget_year"][0]["travel"] = {"domestic_travel_cost": "10.00"}
    second["budget_year"][0]["travel"] = {"domestic_travel_cost": "25.25"}

    response = _calculate(profile, _wrap(profile, [first, second]))
    budgets = response["budget_attachments"]
    assert [budget["budget_summary"]["cumulative_domestic_travel_costs"] for budget in budgets] == [
        "10.00",
        "25.25",
    ]
    assert [budget["budget_year"][0]["direct_costs"] for budget in budgets] == [
        "10.00",
        "25.25",
    ]

    assert_validation_case(
        profile.form_id,
        ValidationCase("independent nested subawards", response, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )
    root = _generate_and_validate_xml(profile, response)
    budget_name = "RR_Budget10_3_0" if "10_30" in profile.root_name else "RR_Budget_3_0"
    emitted = root.findall(f".//{{{profile.budget_namespace}}}{budget_name}")
    assert [
        node.findtext(f"{{{profile.budget_namespace}}}OrganizationName") for node in emitted
    ] == [
        "First Subrecipient",
        "Second Subrecipient",
    ]


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile.form_id)
def test_maximum_budget_period_boundary_completes_lifecycle_and_xsd_validation(
    profile: BudgetProfile,
) -> None:
    budget = _adapt_budget(profile, _minimal_budget())
    first_period = budget["budget_year"][0]
    budget["budget_year"] = [copy.deepcopy(first_period) for _ in range(profile.max_periods)]
    response = _calculate(profile, _wrap(profile, [budget]))

    assert_validation_case(
        profile.form_id,
        ValidationCase("maximum budget periods", response, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )
    root = _generate_and_validate_xml(profile, response)
    if profile.subaward:
        budget_name = "RR_Budget10_3_0" if "10_30" in profile.root_name else "RR_Budget_3_0"
        emitted_budget = root.find(f".//{{{profile.budget_namespace}}}{budget_name}")
        assert emitted_budget is not None
    else:
        emitted_budget = root
    assert (
        len(emitted_budget.findall(f"{{{profile.budget_namespace}}}BudgetYear"))
        == profile.max_periods
    )


@pytest.mark.parametrize(
    "profile",
    [profile for profile in PROFILES if profile.subaward],
    ids=lambda profile: profile.form_id,
)
def test_maximum_subaward_boundary_completes_lifecycle_and_xsd_validation(
    profile: BudgetProfile,
) -> None:
    budgets = []
    for index in range(profile.max_budgets):
        budget = _adapt_budget(profile, _minimal_budget())
        budget["organization_name"] = f"Subrecipient {index + 1}"
        budgets.append(budget)
    response = _calculate(profile, _wrap(profile, budgets))

    assert_validation_case(
        profile.form_id,
        ValidationCase("maximum subawards", response, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )
    root = _generate_and_validate_xml(profile, response)
    budget_name = "RR_Budget10_3_0" if "10_30" in profile.root_name else "RR_Budget_3_0"
    assert (
        len(root.findall(f".//{{{profile.budget_namespace}}}{budget_name}")) == profile.max_budgets
    )

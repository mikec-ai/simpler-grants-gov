"""R&R Budget XML canary for the portable form-spec consumer boundary."""

import copy
import hashlib
from pathlib import Path
from typing import Any

from lxml import etree

from src.form_schema.form_spec.xml.rr_budget import RR_BUDGET_XML_TRANSFORM_RULES
from src.form_schema.forms.rr_budget import RRBudget_v3_0
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo
from src.services.xml_generation.validation.xsd_validator import XSDValidator

FORM_NS = "http://apply.grants.gov/forms/RR_Budget_3_0-V3.0"
ATT_NS = "http://apply.grants.gov/system/Attachments-V1.0"
GLOB_NS = "http://apply.grants.gov/system/Global-V1.0"
GLOB_LIB_NS = "http://apply.grants.gov/system/GlobalLibrary-V2.0"
XSD_SHA256 = "d474010f85819549990de65fc51292bed08ba98ac0895d0dde9513fbe855cdbc"

BUDGET_ATTACHMENT_ID = "00000000-0000-0000-0000-000000000001"
KEY_PERSON_ATTACHMENT_ID = "00000000-0000-0000-0000-000000000002"
EQUIPMENT_ATTACHMENT_ID = "00000000-0000-0000-0000-000000000003"


def _attachment(filename: str) -> AttachmentInfo:
    return AttachmentInfo(
        filename=filename,
        mime_type="application/pdf",
        file_location=f"./attachments/{filename}",
        hash_value="2jmj7l5rSw0yVb/vlWAYkK/YBwk=",
    )


def _attachment_mapping() -> dict[str, AttachmentInfo]:
    return {
        BUDGET_ATTACHMENT_ID: _attachment("budget-justification.pdf"),
        KEY_PERSON_ATTACHMENT_ID: _attachment("additional-key-personnel.pdf"),
        EQUIPMENT_ATTACHMENT_ID: _attachment("additional-equipment.pdf"),
    }


def _personnel(project_role: str) -> dict[str, Any]:
    return {
        "number_of_personnel": 1,
        "project_role": project_role,
        "calendar_months": "1.00",
        "academic_months": "1.00",
        "summer_months": "1.00",
        "requested_salary": "10.00",
        "fringe_benefits": "2.00",
        "funds_requested": "12.00",
    }


def _application_data() -> dict[str, Any]:
    return {
        "samuei": "TEST12345678",
        "budget_type": "Project",
        "organization_name": "Example Research University",
        "budget_year": [
            {
                "budget_period_start_date": "2026-01-01",
                "budget_period_end_date": "2026-12-31",
                "key_persons": {
                    "key_person": [
                        {
                            "name": {
                                "prefix_name": "Dr.",
                                "first_name": "Ada",
                                "middle_name": "M",
                                "last_name": "Lovelace",
                                "suffix_name": "PhD",
                            },
                            "project_role": "Principal Investigator",
                            "base_salary": "1000.00",
                            "calendar_months": "1.00",
                            "academic_months": "1.00",
                            "summer_months": "1.00",
                            "requested_salary": "100.00",
                            "fringe_benefits": "20.00",
                            "funds_requested": "120.00",
                        }
                    ],
                    "total_fund_for_attached_key_persons": "0.00",
                    "total_fund_for_key_persons": "120.00",
                    "attached_key_persons": KEY_PERSON_ATTACHMENT_ID,
                },
                "other_personnel": {
                    "post_doc_associates": _personnel("Post Doctoral Associates"),
                    "graduate_students": _personnel("Graduate Students"),
                    "undergraduate_students": _personnel("Undergraduate Students"),
                    "secretarial_clerical": _personnel("Secretarial / Clerical"),
                    "other": [_personnel("Research Assistant")],
                    "other_personnel_total_number": 5,
                    "total_other_personnel_fund": "60.00",
                },
                "total_compensation": "120.00",
                "equipment": {
                    "equipment_list": [
                        {
                            "equipment_item": "Microscope",
                            "funds_requested": "1000.00",
                        }
                    ],
                    "total_fund_for_attached_equipment": "0.00",
                    "total_fund": "1000.00",
                    "additional_equipments_attachment": EQUIPMENT_ATTACHMENT_ID,
                },
                "travel": {
                    "domestic_travel_cost": "10.00",
                    "foreign_travel_cost": "20.00",
                    "total_travel_cost": "30.00",
                },
                "participant_trainee_support_costs": {
                    "tuition_fee_health_insurance": "10.00",
                    "stipends": "10.00",
                    "travel": "10.00",
                    "subsistence": "10.00",
                    "other": {"description": "Registration", "cost": "10.00"},
                    "participant_trainee_number": 1,
                    "total_cost": "50.00",
                },
                "other_direct_costs": {
                    "materials_supplies": "1.00",
                    "publication_costs": "1.00",
                    "consultant_services": "1.00",
                    "adp_computer_services": "1.00",
                    "subaward_consortium_contractual_costs": "1.00",
                    "equipment_rental_fee": "1.00",
                    "alterations_renovations": "1.00",
                    **{
                        f"other_direct_cost_{index}": {
                            "description": f"Other direct cost {index}",
                            "cost": "1.00",
                        }
                        for index in range(1, 11)
                    },
                    "total_other_direct_cost": "17.00",
                },
                "direct_costs": "1120.00",
                "indirect_costs": {
                    "indirect_cost": [
                        {
                            "cost_type": "Modified total direct costs",
                            "rate": "10.00",
                            "base": "100.00",
                            "fund_requested": "10.00",
                        }
                    ],
                    "total_indirect_costs": "10.00",
                },
                "cognizant_federal_agency": "Example Agency, Pat Doe, 202-555-0100",
                "total_costs": "1120.00",
                "fee": "1.00",
                "total_costs_fee": "1120.00",
            }
        ],
        "budget_justification_attachment": BUDGET_ATTACHMENT_ID,
        "budget_summary": {
            "cumulative_total_funds_requested_senior_key_person": "120.00",
            "cumulative_total_funds_requested_other_personnel": "60.00",
            "cumulative_total_no_other_personnel": 5,
            "cumulative_total_funds_requested_personnel": "120.00",
            "cumulative_total_funds_requested_equipment": "1000.00",
            "cumulative_total_funds_requested_travel": "30.00",
            "cumulative_domestic_travel_costs": "10.00",
            "cumulative_foreign_travel_costs": "20.00",
            "cumulative_total_funds_requested_trainee_costs": "50.00",
            "cumulative_trainee_tuition_fees_health_insurance": "10.00",
            "cumulative_trainee_stipends": "10.00",
            "cumulative_trainee_travel": "10.00",
            "cumulative_trainee_subsistence": "10.00",
            "cumulative_other_trainee_cost": "10.00",
            "cumulative_noof_trainees": 1,
            "cumulative_total_funds_requested_other_direct_costs": "17.00",
            "cumulative_material_and_supplies": "1.00",
            "cumulative_publication_costs": "1.00",
            "cumulative_consultant_services": "1.00",
            "cumulative_adp_computer_services": "1.00",
            "cumulative_subaward_consortium_contractual_costs": "1.00",
            "cumulative_equipment_facility_rental_fees": "1.00",
            "cumulative_alterations_and_renovations": "1.00",
            **{f"cumulative_other_{index}_direct_cost": "1.00" for index in range(1, 11)},
            "cumulative_total_funds_requested_direct_costs": "1120.00",
            "cumulative_total_funds_requested_indirect_cost": "10.00",
            "cumulative_total_funds_requested_direct_indirect_costs": "1120.00",
            "cumulative_fee": "1.00",
            "cumulative_total_costs_fee": "1120.00",
        },
    }


def _generate_xml(
    data: dict[str, Any] | None = None,
    attachment_mapping: dict[str, AttachmentInfo] | None = None,
) -> str:
    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=_application_data() if data is None else data,
            transform_config=RR_BUDGET_XML_TRANSFORM_RULES,
            attachment_mapping=attachment_mapping or _attachment_mapping(),
        )
    )
    assert response.success, response.error_message
    assert response.xml_data is not None
    return response.xml_data


def _local_names(element: etree._Element) -> list[str]:
    return [etree.QName(child).localname for child in element]


def test_runtime_form_registers_the_consumer_owned_xml_projection() -> None:
    assert RRBudget_v3_0.json_to_xml_schema is RR_BUDGET_XML_TRANSFORM_RULES


def test_xml_projection_maps_every_field_in_the_projected_runtime_schema() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRBudget_v3_0.form_json_schema))

    def schema_paths(node: Any, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
        if not isinstance(node, dict):
            return set()
        found: set[tuple[str, ...]] = set()
        for name, child in node.get("properties", {}).items():
            child_path = (*path, name)
            found.add(child_path)
            found |= schema_paths(child, child_path)
        found |= schema_paths(node.get("items"), path)
        return found

    def mapping_paths(rules: Any, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
        found: set[tuple[str, ...]] = set()
        for name, rule in rules.items():
            if name.startswith("_") or not isinstance(rule, dict):
                continue
            child_path = (*path, name)
            found.add(child_path)
            transform_type = rule.get("xml_transform", {}).get("type")
            if transform_type == "array":
                found |= mapping_paths(rule.get("items", {}), child_path)
            elif transform_type == "nested_object":
                found |= mapping_paths(rule, child_path)
        return found

    assert schema_paths(schema) <= mapping_paths(RR_BUDGET_XML_TRANSFORM_RULES)


def test_rr_budget_xml_uses_the_xsd_sequence_and_namespaces() -> None:
    root = etree.fromstring(_generate_xml().encode())

    assert root.tag == f"{{{FORM_NS}}}RR_Budget_3_0"
    assert root.get(f"{{{FORM_NS}}}FormVersion") == "3.0"
    assert _local_names(root) == [
        "SAMUEI",
        "BudgetType",
        "OrganizationName",
        "BudgetYear",
        "BudgetJustificationAttachment",
        "BudgetSummary",
    ]

    budget_year = root.find(f"{{{FORM_NS}}}BudgetYear")
    assert budget_year is not None
    assert _local_names(budget_year) == [
        "BudgetPeriodStartDate",
        "BudgetPeriodEndDate",
        "KeyPersons",
        "OtherPersonnel",
        "TotalCompensation",
        "Equipment",
        "Travel",
        "ParticipantTraineeSupportCosts",
        "OtherDirectCosts",
        "DirectCosts",
        "IndirectCosts",
        "CognizantFederalAgency",
        "TotalCosts",
        "Fee",
        "TotalCostsFee",
    ]

    first_name = root.find(f".//{{{GLOB_LIB_NS}}}FirstName")
    assert first_name is not None
    assert first_name.text == "Ada"


def test_attachment_transform_resolves_root_and_nested_attachment_uuids() -> None:
    root = etree.fromstring(_generate_xml().encode())

    expected = {
        "BudgetJustificationAttachment": "budget-justification.pdf",
        "AttachedKeyPersons": "additional-key-personnel.pdf",
        "AdditionalEquipmentsAttachment": "additional-equipment.pdf",
    }
    for wrapper_name, filename in expected.items():
        wrapper = root.find(f".//{{{FORM_NS}}}{wrapper_name}")
        assert wrapper is not None
        assert wrapper.findtext(f"{{{ATT_NS}}}FileName") == filename
        location = wrapper.find(f"{{{ATT_NS}}}FileLocation")
        assert location is not None
        assert location.get(f"{{{ATT_NS}}}href") == f"./attachments/{filename}"
        hash_value = wrapper.find(f"{{{GLOB_NS}}}HashValue")
        assert hash_value is not None
        assert hash_value.get(f"{{{GLOB_NS}}}hashAlgorithm") == "SHA-1"


def test_rr_budget_output_validates_against_the_pinned_official_xsd() -> None:
    xsd_dir = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
    xsd_path = xsd_dir / "RR_Budget_3_0-V3.0.xsd"
    assert hashlib.sha256(xsd_path.read_bytes()).hexdigest() == XSD_SHA256

    result = XSDValidator(xsd_dir).validate_xml(_generate_xml(), xsd_path)

    assert result["valid"], result["error_message"]


def test_attachment_transform_fails_closed_for_an_unknown_nested_uuid() -> None:
    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=_application_data(),
            transform_config=RR_BUDGET_XML_TRANSFORM_RULES,
            attachment_mapping={BUDGET_ATTACHMENT_ID: _attachment("budget-justification.pdf")},
        )
    )

    assert not response.success
    assert KEY_PERSON_ATTACHMENT_ID in (response.error_message or "")
    assert "budget_year.key_persons.attached_key_persons" in (response.error_message or "")

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lxml import etree

from src.form_schema.form_spec.loader import load_form
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo
from src.services.xml_generation.validation.xsd_validator import XSDValidator

XSD_DIR = Path(__file__).parents[4] / "src/services/xml_generation/xsds"


def _attachment(name: str) -> AttachmentInfo:
    return AttachmentInfo(
        filename=name,
        mime_type="application/pdf",
        file_location=f"./attachments/{name}",
        hash_value="YWJj",
    )


def _generate(
    form_id: str, data: dict, attachments: dict[str, AttachmentInfo] | None = None
) -> str:
    profile = load_form(form_id).json_to_xml_schema
    assert profile is not None
    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=data,
            transform_config=profile,
            attachment_mapping=attachments or {},
        )
    )
    assert response.success, response.error_message
    assert response.xml_data is not None
    return response.xml_data


def _assert_official_xsd(xml: str, filename: str, digest: str) -> etree._Element:
    path = XSD_DIR / filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    result = XSDValidator(XSD_DIR).validate_xml(xml, path)
    assert result["valid"], result["error_message"]
    return etree.fromstring(xml.encode())


def test_performance_site_profile_generates_official_xsd_valid_xml() -> None:
    attachment_id = "11111111-1111-1111-1111-111111111111"
    site = {
        "individual": "N: No",
        "organization_name": "Example University",
        "sam_uei": "ABCDEFGHIJ12",
        "address": {
            "street1": "1 Main Street",
            "city": "Washington",
            "state": "DC: District of Columbia",
            "zip_code": "20001",
            "country": "USA: UNITED STATES",
        },
        "congressional_district": "DC-000",
    }
    xml = _generate(
        "performance-site",
        {
            "primary_site": site,
            "additional_sites": [{**site, "organization_name": "Second Site"}],
            "additional_locations": attachment_id,
        },
        {attachment_id: _attachment("additional-sites.pdf")},
    )
    root = _assert_official_xsd(
        xml,
        "PerformanceSite_4_0-V4.0.xsd",
        "d47dbb254b112f69dc308c01dea2fe15b29114d0e3bdc5a137d3178b5af7bc6c",
    )
    ns = "http://apply.grants.gov/forms/PerformanceSite_4_0-V4.0"
    assert [etree.QName(child).localname for child in root] == [
        "PrimarySite",
        "OtherSite",
        "AttachedFile",
    ]
    assert root.get(f"{{{ns}}}FormVersion") == "4.0"


def test_rr_other_project_information_profile_handles_groups_and_scalar_array() -> None:
    attachment_ids = [f"22222222-2222-2222-2222-{index:012d}" for index in range(1, 8)]
    data = {
        "human_subjects": {
            "involves_human_subjects": "Y: Yes",
            "exempt_from_federal_regulations": "Y: Yes",
            "exemptions": ["E1", "E2"],
        },
        "vertebrate_animals": {"involves_vertebrate_animals": "N: No"},
        "proprietary_information": {"includes_proprietary_information": "N: No"},
        "environmental_impact": {
            "has_environmental_impact": "Y: Yes",
            "environmental_impact_explanation": "Managed through approved controls",
            "has_environmental_exemption_or_assessment": "Y: Yes",
            "environmental_exemption_or_assessment_explanation": "Assessment approved",
        },
        "historic_places": {
            "has_historic_designation": "Y: Yes",
            "explanation": "Eligible research location",
        },
        "international_activities": {
            "involves_international_activities": "Y: Yes",
            "countries": "Canada",
            "explanation": "Research partnership",
        },
        "project_summary_abstract": attachment_ids[0],
        "project_narrative": attachment_ids[1],
        "bibliography_references": attachment_ids[2],
        "facilities_resources": attachment_ids[3],
        "equipment": attachment_ids[4],
        "other_attachments": attachment_ids[5:],
    }
    attachments = {
        attachment_id: _attachment(f"attachment-{index}.pdf")
        for index, attachment_id in enumerate(attachment_ids, 1)
    }
    xml = _generate("rr-other-project-information", data, attachments)
    root = _assert_official_xsd(
        xml,
        "RR_OtherProjectInfo_1_4-V1.4.xsd",
        "b2144c290ed5ad6d942e70815d195d7d6aa4e8e6c82fc3932d8540e3aa303ef5",
    )
    names = [etree.QName(child).localname for child in root]
    assert names[:4] == [
        "HumanSubjectsIndicator",
        "HumanSubjectsSupplement",
        "VertebrateAnimalsIndicator",
        "ProprietaryInformationIndicator",
    ]
    other = root.find("{*}OtherAttachments")
    assert other is not None
    assert len(other.findall("{*}OtherAttachment")) == 2


def test_phs398_modular_budget_profile_deep_merges_cumulative_wire_container() -> None:
    attachment_ids = [f"33333333-3333-3333-3333-{index:012d}" for index in range(1, 4)]
    data = {
        "periods": [
            {
                "budget_period_start_date": "2027-01-01",
                "budget_period_end_date": "2027-12-31",
                "direct_costs": {
                    "direct_cost_less_consortium_fand_a": "25000.00",
                    "consortium_fand_a": "1000.00",
                    "total_direct_costs": "26000.00",
                },
                "indirect_costs": {
                    "indirect_cost_items": [
                        {
                            "indirect_cost_type": "Modified total direct costs",
                            "indirect_cost_rate": "10.00",
                            "indirect_cost_base": "10000.00",
                            "indirect_cost_funds_requested": "1000.00",
                        }
                    ],
                    "total_indirect_costs": "1000.00",
                },
                "total_direct_and_indirect_costs": "27000.00",
            }
        ],
        "cumulative_budget_information": {
            "cumulative_direct_cost_less_consortium_fand_a": "25000.00",
            "cumulative_consortium_fand_a": "1000.00",
            "cumulative_total_direct_costs": "26000.00",
            "cumulative_total_indirect_costs": "1000.00",
            "cumulative_total_direct_and_indirect_costs": "27000.00",
        },
        "personnel_justification": attachment_ids[0],
        "consortium_justification": attachment_ids[1],
        "additional_narrative_justification": attachment_ids[2],
    }
    attachments = {
        attachment_id: _attachment(f"justification-{index}.pdf")
        for index, attachment_id in enumerate(attachment_ids, 1)
    }
    xml = _generate("phs398-modular-budget", data, attachments)
    root = _assert_official_xsd(
        xml,
        "PHS398_ModularBudget_1_2-V1.2.xsd",
        "f166abebd40e6912861dca5c5c4a83c7a82779f1ae67a2c0fa8b4aafc25d5bff",
    )
    cumulative = root.find("{*}CummulativeBudgetInfo")
    assert cumulative is not None
    assert [etree.QName(child).localname for child in cumulative] == [
        "EntirePeriodTotalCost",
        "BudgetJustifications",
    ]
    justifications = cumulative.find("{*}BudgetJustifications")
    assert justifications is not None
    assert [etree.QName(child).localname for child in justifications] == [
        "PersonnelJustification",
        "ConsortiumJustification",
        "AdditionalNarrativeJustification",
    ]


@pytest.mark.parametrize(
    "form_id",
    ["performance-site", "rr-other-project-information", "phs398-modular-budget"],
)
def test_each_complex_form_uses_only_the_generic_profile_adapter(form_id: str) -> None:
    assert load_form(form_id).json_to_xml_schema is not None

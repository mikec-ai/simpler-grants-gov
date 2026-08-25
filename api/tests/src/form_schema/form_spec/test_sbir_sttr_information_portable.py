"""Technical closure evidence for the unregistered SBIR/STTR Information package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form, load_form
from src.form_schema.form_spec.preview import build_preview_form, preview_form_id
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator

FORM_ID = "sbir-sttr-information"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID
XSD = Path("src/services/xml_generation/xsds/SBIR_STTR_Information_3_0-V3.0.xsd")
XSD_DIRECTORY = XSD.parent
XSD_SHA256 = "32ed46a450c1b77d9ef64ebf2a4086ab90b076aa2d3cdfedfab8c00324adcebf"
COMPILED_PATHS = {
    "otherAgency",
    "agencyTopicSubtopic",
    "federalSubcontractorNames",
    "nonDomesticPerformanceExplanation",
    "equivalentWorkFederalAgencies",
    "phaseIIAwardsReceived.value",
    "commercializationHistory",
    "pdpiPrimaryEmployment.value",
    "pdpiAppointmentAndEffort.value",
    "jointPerformancePercentage.value",
    "nonprofitResearchPartnerUei",
}
UNCOMPILED_PATHS = {
    "/otherAgency",
    "/federalSubcontractorNames",
    "/nonDomesticPerformanceExplanation",
    "/equivalentWorkFederalAgencies",
    "/commercializationPlan",
}


def _read(relative: str) -> dict:
    return json.loads((FORM_ROOT / relative).read_text())


def _resolved_schema() -> dict:
    # The source-authored portable contract intentionally retains canonical paths;
    # consumer projection separately normalizes those paths for SGG runtime use.
    return _read("schema.json")


def _conditional_contract(schema: dict, required: set[str]) -> dict:
    [contract] = [
        condition for condition in schema["allOf"] if set(condition["then"]["required"]) == required
    ]
    return contract


def test_exact_package_is_preview_only_and_preserves_review_boundaries() -> None:
    manifest = _read("manifest.json")
    evidence = _read("evidence.json")

    assert manifest["form"] == {
        "id": FORM_ID,
        "legacyFormId": 787,
        "formName": "SBIR/STTR Information",
        "shortFormName": "SBIR_STTR_Information_3_0",
        "formVersion": "3.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
    }
    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 27
    assert all(
        mapping["status"] == "proposed" for mapping in evidence["semanticReview"]["mappings"]
    )

    by_status: dict[str, set[str]] = {}
    for record in evidence["behaviorEvidence"]:
        by_status.setdefault(record["executionStatus"], set()).add(record["canonicalPath"])
    assert by_status == {
        "compiled": COMPILED_PATHS,
        "source-bound-uncompiled": UNCOMPILED_PATHS,
    }

    sources = {source["id"]: source for source in evidence["sources"]}
    assert sources["sbir-sttr-xsd-v3-0"]["sha256"] == XSD_SHA256
    assert sources["sbir-sttr-dat-f787"]["sha256"] == (
        "c0e8d91e583b9f7e6339cc6239f1e4d51e9d93299b893b34efd1bbbc435c6e9b"
    )
    assert sources["sbir-sttr-grants-gov-xfa-pdf-v3-0"]["sha256"] == (
        "bd36dbc83d8fcfcd309cd45236d496a5f34f1401b4cf51d5aaeac2f22e45ce1e"
    )
    assert hashlib.sha256(XSD.read_bytes()).hexdigest() == XSD_SHA256

    preview = build_preview_form(FORM_ID)
    assert preview.form_id == preview_form_id(FORM_ID)
    assert preview.form_name == "[Portable preview] SBIR/STTR Information"
    assert len(preview.form_json_schema["properties"]) == 27

    with pytest.raises(ValueError, match="no SGG runtime identity"):
        runtime_identity(FORM_ID)
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        load_form(FORM_ID)


@pytest.mark.parametrize(
    ("required", "active", "inactive"),
    [
        ({"otherAgency"}, {"agency": {"value": "Other"}}, {"agency": {"value": "NIH"}}),
        (
            {"agencyTopicSubtopic"},
            {"agency": {"value": "DOE"}},
            {"agency": {"value": "NIH"}},
        ),
        (
            {"federalSubcontractorNames"},
            {"federalSubcontractsIncluded": {"value": "Y: Yes"}},
            {"federalSubcontractsIncluded": {"value": "N: No"}},
        ),
        (
            {"nonDomesticPerformanceExplanation"},
            {"domesticPerformance": {"value": "N: No"}},
            {"domesticPerformance": {"value": "Y: Yes"}},
        ),
        (
            {"equivalentWorkFederalAgencies"},
            {"equivalentFederalWork": {"value": "Y: Yes"}},
            {"equivalentFederalWork": {"value": "N: No"}},
        ),
        (
            {
                "phaseIIAwardsReceived",
                "pdpiPrimaryEmployment",
                "pdpiAppointmentAndEffort",
                "jointPerformancePercentage",
                "nonprofitResearchPartnerUei",
            },
            {"programType": {"value": "Both"}},
            {"programType": {"value": "Other"}},
        ),
        (
            {"phaseIIAwardsReceived", "pdpiPrimaryEmployment"},
            {"programType": {"value": "SBIR"}},
            {"programType": {"value": "Other"}},
        ),
        (
            {
                "pdpiAppointmentAndEffort",
                "jointPerformancePercentage",
                "nonprofitResearchPartnerUei",
            },
            {"programType": {"value": "STTR"}},
            {"programType": {"value": "Other"}},
        ),
        (
            {"commercializationHistory"},
            {"phaseIIAwardsReceived": {"value": "Y: Yes"}},
            {"phaseIIAwardsReceived": {"value": "N: No"}},
        ),
    ],
)
def test_all_source_bound_conditional_required_transitions_execute(
    required: set[str], active: dict, inactive: dict
) -> None:
    contract = _conditional_contract(_resolved_schema(), required)
    validator = Draft202012Validator(contract)

    assert not validator.is_valid(active)
    assert validator.is_valid(inactive)
    assert validator.is_valid({**active, **{field: {} for field in required}})


def test_three_distinct_attachments_use_the_shared_attachment_mechanism() -> None:
    rule_schema = _read("sgg/rule-schema.json")
    xml_profile = _read("targets/grants-gov-xml.json")
    attachment_fields = {
        "nonDomesticPerformanceExplanation": "NonDomesticPerformanceExplanation",
        "commercializationPlan": "CommercializationPlan",
        "commercializationHistory": "SBIR_CommercializationHistory",
    }

    assert set(rule_schema) == set(attachment_fields)
    for field, element in attachment_fields.items():
        assert rule_schema[field] == {"gg_validation": {"rule": "attachment"}}
        assert xml_profile["mapping"]["fields"][field] == {
            "element": element,
            "kind": "attachment",
            "namespace": "default",
            "source": f"/{field}",
        }

    assert xml_profile["xsd"] == {
        "uri": "https://apply07.grants.gov/apply/forms/schemas/SBIR_STTR_Information_3_0-V3.0.xsd",
        "sha256": XSD_SHA256,
    }


def test_representative_sttr_response_emits_exact_xsd_valid_xml() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=True)
    response = {
        "agency": {"value": "HHS"},
        "sbc_control_id": "123456789",
        "program_type": {"value": "STTR"},
        "application_type": {"value": "Phase I"},
        "small_business_eligibility": {"value": "Y: Yes"},
        "number_of_employees": 42,
        "vcoc_ownership": {"value": "N: No"},
        "faculty_student_ownership": {"value": "N: No"},
        "federal_subcontracts_included": {"value": "N: No"},
        "hubzone_location": {"value": "N: No"},
        "domestic_performance": {"value": "Y: Yes"},
        "equivalent_federal_work": {"value": "N: No"},
        "disclosure_permission": {"value": "Y: Yes"},
        "taba_funding_request": {"value": "N: No"},
        "pdpi_appointment_and_effort": {"value": "Y: Yes"},
        "joint_performance_percentage": {"value": "Y: Yes"},
        "nonprofit_research_partner_uei": "ABCDEFGHIJKL",
    }

    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=projected.json_to_xml_schema,
        )
    )

    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    assert "<SBIR_STTR_Information_3_0:ProgramType>STTR</" in generated.xml_data
    assert "<SBIR_STTR_Information_3_0:SAMUEI>ABCDEFGHIJKL</" in generated.xml_data
    validation = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(generated.xml_data, XSD.stem)
    assert validation["valid"], validation

"""Technical closure evidence for the unregistered SBIR/STTR Information package."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form, load_form
from src.form_schema.form_spec.preview import build_preview_form, preview_form_id
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo
from src.services.xml_generation.validation.xsd_validator import XSDValidator

FORM_ID = "sbir-sttr-information"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID
XSD = Path("src/services/xml_generation/xsds/SBIR_STTR_Information_3_0-V3.0.xsd")
XSD_DIRECTORY = XSD.parent
XSD_SHA256 = "32ed46a450c1b77d9ef64ebf2a4086ab90b076aa2d3cdfedfab8c00324adcebf"
PROJECTED_CONDITIONS = Path(__file__).with_name("sbir_sttr_projected_conditions.json")
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
    return _load_banked_form(FORM_ID, project_xml=False).form_json_schema


def _projected_conditions() -> list[dict]:
    projected = _load_banked_form(FORM_ID, project_xml=False)

    def walk(nodes: list[dict]):
        for node in nodes:
            yield node
            if node.get("type") in {"section", "fieldList"}:
                yield from walk(node.get("children", []))

    return [
        {"definition": node["definition"], "conditional": node["conditional"]}
        for node in walk(projected.form_ui_schema)
        if node.get("conditional") is not None
    ]


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


def test_frontend_condition_fixture_is_exact_consumer_adapter_output() -> None:
    assert json.loads(PROJECTED_CONDITIONS.read_text()) == _projected_conditions()


@pytest.mark.parametrize(
    ("required", "active", "inactive"),
    [
        ({"other_agency"}, {"agency": {"value": "Other"}}, {"agency": {"value": "NIH"}}),
        (
            {"agency_topic_subtopic"},
            {"agency": {"value": "DOE"}},
            {"agency": {"value": "NIH"}},
        ),
        (
            {"federal_subcontractor_names"},
            {"federal_subcontracts_included": {"value": "Y: Yes"}},
            {"federal_subcontracts_included": {"value": "N: No"}},
        ),
        (
            {"non_domestic_performance_explanation"},
            {"domestic_performance": {"value": "N: No"}},
            {"domestic_performance": {"value": "Y: Yes"}},
        ),
        (
            {"equivalent_work_federal_agencies"},
            {"equivalent_federal_work": {"value": "Y: Yes"}},
            {"equivalent_federal_work": {"value": "N: No"}},
        ),
        (
            {
                "phase_iiawards_received",
                "pdpi_primary_employment",
                "pdpi_appointment_and_effort",
                "joint_performance_percentage",
                "nonprofit_research_partner_uei",
            },
            {"program_type": {"value": "Both"}},
            {"program_type": {"value": "Other"}},
        ),
        (
            {"phase_iiawards_received", "pdpi_primary_employment"},
            {"program_type": {"value": "SBIR"}},
            {"program_type": {"value": "Other"}},
        ),
        (
            {
                "pdpi_appointment_and_effort",
                "joint_performance_percentage",
                "nonprofit_research_partner_uei",
            },
            {"program_type": {"value": "STTR"}},
            {"program_type": {"value": "Other"}},
        ),
        (
            {"commercialization_history"},
            {"phase_iiawards_received": {"value": "Y: Yes"}},
            {"phase_iiawards_received": {"value": "N: No"}},
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


def test_all_three_projected_attachments_execute_shared_validation_and_xml() -> None:
    attachment_ids = {
        "non_domestic_performance_explanation": "11111111-1111-1111-1111-111111111111",
        "commercialization_plan": "22222222-2222-2222-2222-222222222222",
        "commercialization_history": "33333333-3333-3333-3333-333333333333",
    }
    projected = _load_banked_form(FORM_ID, project_xml=True)
    response = {
        "agency": {"value": "HHS"},
        "sbc_control_id": "123456789",
        "program_type": {"value": "SBIR"},
        "application_type": {"value": "Phase II"},
        "small_business_eligibility": {"value": "Y: Yes"},
        "number_of_employees": 42,
        "vcoc_ownership": {"value": "N: No"},
        "faculty_student_ownership": {"value": "N: No"},
        "federal_subcontracts_included": {"value": "N: No"},
        "hubzone_location": {"value": "N: No"},
        "domestic_performance": {"value": "N: No"},
        "equivalent_federal_work": {"value": "N: No"},
        "disclosure_permission": {"value": "Y: Yes"},
        "taba_funding_request": {"value": "N: No"},
        "phase_iiawards_received": {"value": "Y: Yes"},
        "pdpi_primary_employment": {"value": "Y: Yes"},
        **attachment_ids,
    }
    application = SimpleNamespace(
        application_attachments=[
            SimpleNamespace(application_attachment_id=uuid.UUID(attachment_id))
            for attachment_id in attachment_ids.values()
        ]
    )
    application_form = SimpleNamespace(
        application_response=response,
        application_form_id=uuid.uuid4(),
        form_id=preview_form_id(FORM_ID),
        application=application,
        form=SimpleNamespace(form_rule_schema=projected.form_rule_schema),
    )
    context = JsonRuleContext(
        application_form,
        JsonRuleConfig(do_pre_population=False, do_post_population=False),
    )

    process_rule_schema_for_context(context)

    assert context.validation_issues == []
    assert context.attachment_ids == set(attachment_ids.values())

    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=context.json_data,
            transform_config=projected.json_to_xml_schema,
            attachment_mapping={
                attachment_id: AttachmentInfo(
                    filename=f"{field}.pdf",
                    mime_type="application/pdf",
                    file_location=f"./attachments/{field}.pdf",
                    hash_value="YWJjZA==",
                )
                for field, attachment_id in attachment_ids.items()
            },
        )
    )

    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    for field in attachment_ids:
        assert f"<att:FileName>{field}.pdf</att:FileName>" in generated.xml_data
    validation = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(generated.xml_data, XSD.stem)
    assert validation["valid"], validation


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

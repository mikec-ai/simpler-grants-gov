"""R&R Multi-Project Cover technical handoff evidence.

The form remains unregistered. These tests exercise its exact banked package through
Simpler's generic preview, validation, submission, and XML boundaries without
claiming human semantic, policy, accessibility, or release approval.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import xmlschema
from lxml import etree

from src.constants.lookup_constants import ApplicationFormStatus
from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form
from src.form_schema.form_spec.preview import build_preview_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.services.applications.application_validation import (
    ApplicationAction,
    validate_application_form,
)
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo

FORM_ID = "rr-sf424-multi-project-cover"
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
XSD_NAME = "RR_SF424_Multi_Project_Cover_4_0-V4.0.xsd"
XSD_SHA256 = "5d5599068d721e6554fa442df88711f8d9386a5fafc18b01cb1d1becc41f84e7"
FORM_NAMESPACE = "http://apply.grants.gov/forms/RR_SF424_Multi_Project_Cover_4_0-V4.0"

REPRESENTATIVE_RESPONSE = {
    "submission_type_code": "Application",
    "submitted_date": "2026-08-25",
    "grants_tracking_number": "1234567890123",
    "project_title": "Portable multi-project cover",
    "proposed_project_period": {
        "proposed_start_date": "2026-09-01",
        "proposed_end_date": "2027-08-31",
    },
    "applicant_congressional_district": "VA-008",
    "estimated_project_funding": {
        "total_estimated_amount": 100,
        "total_non_federal_requested": 25,
        "total_federal_non_federal_requested": 125,
        "estimated_program_income": 0,
    },
    "state_review": {"state_review_code_type": "Program is not covered by E.O. 12372"},
    "trust_agree": "Y: Yes",
    "aor_signature": "Authorized Representative",
    "aor_signed_date": "2026-08-25",
}

ATTACHMENTS = {
    attachment_id: AttachmentInfo(
        filename=filename,
        mime_type="application/pdf",
        file_location=f"./attachments/{filename}",
        hash_value="YWJjZA==",
    )
    for attachment_id, filename in (
        ("sflll", "SFLLL.pdf"),
        ("pre-application", "PreApplication.pdf"),
        ("cover-letter", "CoverLetter.pdf"),
    )
}


def _application_form(response: dict[str, Any]) -> ApplicationForm:
    form = build_preview_form(FORM_ID)
    return cast(
        ApplicationForm,
        SimpleNamespace(
            application_response=copy.deepcopy(response),
            application=SimpleNamespace(
                submitted_by_user=SimpleNamespace(email="reviewer@example.gov"),
                application_attachments=[],
            ),
            application_form_id="rr-sf424-multi-project-cover-lifecycle-test",
            form_id=form.form_id,
            form=form,
            competition_form=SimpleNamespace(is_required=True),
            application_form_status=ApplicationFormStatus.IN_PROGRESS,
        ),
    )


def _validation_fields(response: dict[str, Any], action: ApplicationAction) -> set[str]:
    errors = validate_application_form(_application_form(response), action)
    return {error.field for error in errors if error.field is not None}


def _generate_xml(response: dict[str, Any]) -> str:
    projected = _load_banked_form(FORM_ID)
    assert projected.json_to_xml_schema is not None
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=projected.json_to_xml_schema,
            attachment_mapping=ATTACHMENTS,
        )
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    return generated.xml_data


def test_multi_project_preview_preserves_source_optional_cardinality() -> None:
    form = build_preview_form(FORM_ID)

    assert form.form_name == ("[Portable preview] [Draft] Research & Related Multi-Project Cover")
    assert form.form_version == "4.0"
    assert form.legacy_form_id == 769
    assert form.form_json_schema.get("required", []) == []
    assert len(form.form_json_schema["properties"]) == 28
    assert "grants_tracking_number" in form.form_json_schema["properties"]
    assert "grants_gov_tracking_id" not in form.form_json_schema["properties"]


def test_empty_and_representative_responses_cross_validation_and_submission() -> None:
    assert _validation_fields({}, ApplicationAction.GET) == set()
    assert _validation_fields(REPRESENTATIVE_RESPONSE, ApplicationAction.GET) == set()

    application_form = cast(Any, _application_form(REPRESENTATIVE_RESPONSE))
    assert validate_application_form(application_form, ApplicationAction.SUBMIT) == []
    assert application_form.application_form_status is ApplicationFormStatus.COMPLETE
    assert application_form.application_response == REPRESENTATIVE_RESPONSE


def test_tracking_number_source_length_is_enforced_at_runtime() -> None:
    invalid = copy.deepcopy(REPRESENTATIVE_RESPONSE)
    invalid["grants_tracking_number"] = "too-short"

    assert _validation_fields(invalid, ApplicationAction.GET) == {"$.grants_tracking_number"}


def test_representative_xml_validates_the_exact_official_xsd() -> None:
    xml_response = {
        **REPRESENTATIVE_RESPONSE,
        "sflll_attachment": "sflll",
        "pre_application_attachment": "pre-application",
        "cover_letter_attachment": "cover-letter",
    }
    xml = _generate_xml(xml_response)
    xsd_path = XSD_DIRECTORY / XSD_NAME

    assert hashlib.sha256(xsd_path.read_bytes()).hexdigest() == XSD_SHA256
    locations = {
        "http://apply.grants.gov/system/Attachments-V1.0": str(
            (XSD_DIRECTORY / "Attachments-V1.0.xsd").resolve()
        ),
        "http://apply.grants.gov/system/Global-V1.0": str(
            (XSD_DIRECTORY / "Global-V1.0.xsd").resolve()
        ),
        "http://apply.grants.gov/system/GlobalLibrary-V2.0": str(
            (XSD_DIRECTORY / "GlobalLibrary-V2.0.xsd").resolve()
        ),
        "http://apply.grants.gov/system/UniversalCodes-V2.0": str(
            (XSD_DIRECTORY / "UniversalCodes-V2.0.xsd").resolve()
        ),
    }
    schema = xmlschema.XMLSchema(str(xsd_path.resolve()), locations=locations, allow="local")
    errors = list(schema.iter_errors(xml))
    assert errors == [], "\n".join(str(error) for error in errors)

    root = etree.fromstring(xml.encode())

    def q(name: str) -> str:
        return f"{{{FORM_NAMESPACE}}}{name}"

    assert root.get(q("FormVersion")) == "4.0"
    assert root.findtext(q("GrantsTrackingNumber")) == "1234567890123"
    district = root.find(q("CongressionalDistrict"))
    assert district is not None
    assert district.findtext(q("ApplicantCongressionalDistrict")) == "VA-008"
    assert [child.tag.rsplit("}", 1)[-1] for child in root] == [
        "SubmissionTypeCode",
        "SubmittedDate",
        "GrantsTrackingNumber",
        "ProjectTitle",
        "ProposedProjectPeriod",
        "CongressionalDistrict",
        "EstimatedProjectFunding",
        "StateReview",
        "TrustAgree",
        "SFLLLAttachment",
        "PreApplicationAttachment",
        "CoverLetterAttachment",
        "AOR_Signature",
        "AOR_SignedDate",
    ]


def test_release_and_semantic_gates_remain_explicit() -> None:
    evidence = json.loads((ARTIFACTS / "forms" / FORM_ID / "evidence.json").read_text())
    manifest = json.loads((ARTIFACTS / "forms" / FORM_ID / "manifest.json").read_text())
    registrations = json.loads(REGISTRATIONS.read_text())

    assert manifest["artifacts"]["targets/grants-gov-xml.json"] == "generated"
    assert evidence["semanticReview"]["status"] == "proposed"
    assert all(
        mapping["status"] == "proposed" for mapping in evidence["semanticReview"]["mappings"]
    )
    assert FORM_ID not in registrations["forms"]

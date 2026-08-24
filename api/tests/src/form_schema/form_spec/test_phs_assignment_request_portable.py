"""PHS Assignment Request human-review handoff evidence.

The form is banked but intentionally unregistered. These tests exercise the exact
banked package through Simpler's generic preview, validation, submission, and XML
boundaries without granting it a production runtime identity.
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

FORM_ID = "phs-assignment-request"
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
XSD_NAME = "PHS_AssignmentRequestForm_4_0-V4.0.xsd"
XSD_SHA256 = "7e697ee33ea6f72271c0d74fc48c61f4f81faa242a712a4c73e7898f6c4ab976"
FORM_NAMESPACE = "http://apply.grants.gov/forms/PHS_AssignmentRequestForm_4_0-V4.0"

REPRESENTATIVE_RESPONSE = {
    "suggested_awarding_component1": "NCI",
    "suggested_awarding_component2": "NIAID",
    "suggested_awarding_component3": "NHLBI",
    "suggested_study_section1": "BP10",
    "suggested_study_section2": "IMM-A",
    "suggested_study_section3": "CADO",
    "rationale_suggestions": (
        "The proposed science aligns with the listed institutes and review groups."
    ),
    "expertise1": "Tumor immunology",
    "expertise2": "Vaccine development",
    "expertise3": "Cardiovascular biology",
    "expertise4": "Biostatistics",
    "expertise5": "Implementation science",
    "not_review": (
        "Dr. Example, Example University — recent collaborator; please exclude from review."
    ),
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
            application_form_id="phs-assignment-request-lifecycle-test",
            form_id=form.form_id,
            form=form,
            competition_form=SimpleNamespace(is_required=True),
            application_form_status=ApplicationFormStatus.IN_PROGRESS,
        ),
    )


def _validation_fields(response: dict[str, Any], action: ApplicationAction) -> set[str]:
    application_form = _application_form(response)
    errors = validate_application_form(application_form, action)
    return {error.field for error in errors}


def _generate_xml(response: dict[str, Any]) -> str:
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


def test_assignment_request_preview_preserves_all_source_defined_optional_slots() -> None:
    form = build_preview_form(FORM_ID)
    properties = form.form_json_schema["properties"]

    assert form.form_name == "[Portable preview] PHS Assignment Request Form"
    assert form.form_version == "4.0"
    assert form.legacy_form_id == 833
    assert form.form_json_schema.get("required", []) == []
    assert set(properties) == {
        "suggested_awarding_component1",
        "suggested_awarding_component2",
        "suggested_awarding_component3",
        "suggested_study_section1",
        "suggested_study_section2",
        "suggested_study_section3",
        "rationale_suggestions",
        "expertise1",
        "expertise2",
        "expertise3",
        "expertise4",
        "expertise5",
        "not_review",
    }
    assert [
        properties[f"suggested_awarding_component{index}"]["allOf"][0]["maxLength"]
        for index in range(1, 4)
    ] == [7, 7, 7]
    assert [
        properties[f"suggested_study_section{index}"]["allOf"][0]["maxLength"]
        for index in range(1, 4)
    ] == [20, 20, 20]
    assert [properties[f"expertise{index}"]["allOf"][0]["maxLength"] for index in range(1, 6)] == [
        40
    ] * 5
    assert properties["rationale_suggestions"]["allOf"][0]["maxLength"] == 1000
    assert properties["not_review"]["allOf"][0]["maxLength"] == 1000


def test_assignment_request_optional_and_full_responses_survive_validation_and_submission() -> None:
    assert _validation_fields({}, ApplicationAction.GET) == set()
    assert _validation_fields(REPRESENTATIVE_RESPONSE, ApplicationAction.GET) == set()

    application_form = _application_form(REPRESENTATIVE_RESPONSE)
    assert validate_application_form(application_form, ApplicationAction.SUBMIT) == []
    assert application_form.application_form_status is ApplicationFormStatus.COMPLETE
    assert application_form.application_response == REPRESENTATIVE_RESPONSE
    assert json.loads(json.dumps(application_form.application_response, sort_keys=True)) == (
        REPRESENTATIVE_RESPONSE
    )


def test_assignment_request_enforces_source_declared_limits_at_the_runtime_boundary() -> None:
    invalid = copy.deepcopy(REPRESENTATIVE_RESPONSE)
    invalid.update(
        {
            "suggested_awarding_component1": "TOO-LONG",
            "suggested_study_section2": "S" * 21,
            "expertise5": "E" * 41,
            "rationale_suggestions": "R" * 1001,
            "not_review": "N" * 1001,
        }
    )

    assert _validation_fields(invalid, ApplicationAction.GET) == {
        "$.suggested_awarding_component1",
        "$.suggested_study_section2",
        "$.expertise5",
        "$.rationale_suggestions",
        "$.not_review",
    }


def test_assignment_request_xml_preserves_all_preferences_and_validates_pinned_xsd() -> None:
    xml = _generate_xml(REPRESENTATIVE_RESPONSE)
    xsd_path = XSD_DIRECTORY / XSD_NAME

    assert hashlib.sha256(xsd_path.read_bytes()).hexdigest() == XSD_SHA256
    locations = {
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
    assert [root.findtext(q(f"SuggestedAwardingComponent{index}")) for index in range(1, 4)] == [
        "NCI",
        "NIAID",
        "NHLBI",
    ]
    assert [root.findtext(q(f"SuggestedStudySection{index}")) for index in range(1, 4)] == [
        "BP10",
        "IMM-A",
        "CADO",
    ]
    assert [root.findtext(q(f"Expertise{index}")) for index in range(1, 6)] == [
        "Tumor immunology",
        "Vaccine development",
        "Cardiovascular biology",
        "Biostatistics",
        "Implementation science",
    ]
    assert root.findtext(q("NotReview")) == REPRESENTATIVE_RESPONSE["not_review"]


def test_assignment_request_evidence_and_release_boundaries_remain_explicit() -> None:
    evidence = json.loads((ARTIFACTS / "forms" / FORM_ID / "evidence.json").read_text())
    registrations = json.loads(REGISTRATIONS.read_text())

    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "artifact": "artifacts/proof/grantsgov-PHSAssignmentRequest.jsonl.manifest.json",
        "sourceSetSha256": "63ef51469ecffd0b7a39bd58f827ebe88bc60e8d368ed0789e4608a862660b4b",
        "extractedAt": "2026-08-18T17:32:16.952391Z",
    }
    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 13
    assert all(
        mapping["status"] == "proposed" for mapping in evidence["semanticReview"]["mappings"]
    )
    assert FORM_ID not in registrations["forms"]

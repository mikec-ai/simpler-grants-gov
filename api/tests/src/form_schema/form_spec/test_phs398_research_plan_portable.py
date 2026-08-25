"""PHS 398 Research Plan technical handoff evidence.

The form remains an unregistered preview. These checks exercise its exact banked
package through Simpler's generic validation, attachment, XML, and XSD boundaries
without implementing application-level policy predicates as form-local rules.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
from src.services.xml_generation.validation.xsd_validator import XSDValidator

FORM_ID = "phs398-research-plan"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
XSD_NAME = "PHS398_ResearchPlan_5_0-V5.0.xsd"
XSD_SHA256 = "6e7171465d1f44a16eb822f8921423ceede4fa486cb0819bc5dd327121b4bb56"
FORM_NAMESPACE = "http://apply.grants.gov/forms/PHS398_ResearchPlan_5_0-V5.0"
ATTACHMENT_NAMESPACE = "http://apply.grants.gov/system/Attachments-V1.0"

RESEARCH_STRATEGY_ID = "11111111-1111-1111-1111-111111111111"
APPENDIX_IDS = tuple(f"22222222-2222-2222-2222-{index:012d}" for index in range(1, 11))
MINIMAL_RESPONSE = {"research_strategy": RESEARCH_STRATEGY_ID}
MAXIMUM_APPENDIX_RESPONSE = {
    **MINIMAL_RESPONSE,
    "appendix": list(APPENDIX_IDS),
}


def _attachment_mapping(*attachment_ids: str) -> dict[str, AttachmentInfo]:
    return {
        attachment_id: AttachmentInfo(
            filename=f"document-{index}.pdf",
            mime_type="application/pdf",
            file_location=f"./attachments/document-{index}.pdf",
            hash_value="YWJjZA==",
        )
        for index, attachment_id in enumerate(attachment_ids, start=1)
    }


def _generate_xml(response: dict[str, object], *attachment_ids: str) -> str:
    projected = _load_banked_form(FORM_ID, project_xml=True)
    assert projected.json_to_xml_schema is not None
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=projected.json_to_xml_schema,
            attachment_mapping=_attachment_mapping(*attachment_ids),
        )
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    return generated.xml_data


def _application_form(
    response: dict[str, Any], *, attachment_ids: tuple[str, ...] = ()
) -> ApplicationForm:
    form = build_preview_form(FORM_ID)
    return cast(
        ApplicationForm,
        SimpleNamespace(
            application_response=copy.deepcopy(response),
            application=SimpleNamespace(
                submitted_by_user=SimpleNamespace(email="reviewer@example.gov"),
                application_attachments=[
                    SimpleNamespace(application_attachment_id=attachment_id)
                    for attachment_id in attachment_ids
                ],
            ),
            application_form_id="phs398-research-plan-lifecycle-test",
            form_id=form.form_id,
            form=form,
            competition_form=SimpleNamespace(is_required=True),
            application_form_status=ApplicationFormStatus.IN_PROGRESS,
        ),
    )


def _validation_fields(
    response: dict[str, Any], *, attachment_ids: tuple[str, ...] = ()
) -> set[str]:
    errors = validate_application_form(
        _application_form(response, attachment_ids=attachment_ids),
        ApplicationAction.GET,
    )
    return {error.field for error in errors}


def test_research_plan_preview_preserves_attachment_roles_and_appendix_cap() -> None:
    form = build_preview_form(FORM_ID)
    properties = form.form_json_schema["properties"]

    assert form.form_name == "[Portable preview] PHS 398 Research Plan"
    assert form.form_version == "5.0"
    assert form.legacy_form_id == 797
    assert form.form_json_schema["required"] == ["research_strategy"]
    assert set(properties) == {
        "introduction",
        "specific_aims",
        "research_strategy",
        "progress_report_publication_list",
        "vertebrate_animals",
        "select_agent_research",
        "multiple_pd_pi_leadership_plan",
        "consortium_contractual_arrangements",
        "letters_of_support",
        "resource_sharing_plans",
        "other_plans",
        "key_resource_authentication",
        "appendix",
    }
    # The official XSD container allows 100, while the current applicant policy
    # permits ten. The narrower applicant contract must survive projection.
    assert properties["appendix"]["maxItems"] == 10
    assert form.form_rule_schema is not None
    assert set(form.form_rule_schema) == set(properties)
    assert all(
        rule == {"gg_validation": {"rule": "attachment"}} for rule in form.form_rule_schema.values()
    )


def test_research_plan_validation_and_submit_use_the_generic_attachment_lifecycle() -> None:
    attachment_ids = (RESEARCH_STRATEGY_ID, *APPENDIX_IDS)

    assert _validation_fields({}) == {"$.research_strategy"}
    assert _validation_fields(MAXIMUM_APPENDIX_RESPONSE, attachment_ids=attachment_ids) == set()
    assert _validation_fields(
        {**MINIMAL_RESPONSE, "appendix": [*APPENDIX_IDS, RESEARCH_STRATEGY_ID]},
        attachment_ids=attachment_ids,
    ) == {"$.appendix"}

    submitted = _application_form(MAXIMUM_APPENDIX_RESPONSE, attachment_ids=attachment_ids)
    assert validate_application_form(submitted, ApplicationAction.SUBMIT) == []
    assert submitted.application_form_status is ApplicationFormStatus.COMPLETE
    assert submitted.application_response == MAXIMUM_APPENDIX_RESPONSE
    assert json.loads(json.dumps(submitted.application_response, sort_keys=True)) == (
        MAXIMUM_APPENDIX_RESPONSE
    )


def test_research_plan_xml_flattens_appendix_and_validates_exact_official_xsd() -> None:
    attachment_ids = (RESEARCH_STRATEGY_ID, *APPENDIX_IDS)
    xml = _generate_xml(MAXIMUM_APPENDIX_RESPONSE, *attachment_ids)
    root = etree.fromstring(xml.encode())

    assert root.tag == f"{{{FORM_NAMESPACE}}}PHS398_ResearchPlan_5_0"
    assert root.get(f"{{{FORM_NAMESPACE}}}FormVersion") == "5.0"
    strategy = root.xpath(
        "rp:ResearchPlanAttachments/rp:ResearchStrategy/rp:attFile/att:FileName/text()",
        namespaces={"rp": FORM_NAMESPACE, "att": ATTACHMENT_NAMESPACE},
    )
    assert strategy == ["document-1.pdf"]
    appendix_files = root.xpath(
        "rp:ResearchPlanAttachments/rp:Appendix/att:AttachedFile/att:FileName/text()",
        namespaces={"rp": FORM_NAMESPACE, "att": ATTACHMENT_NAMESPACE},
    )
    assert appendix_files == [f"document-{index}.pdf" for index in range(2, 12)]

    xsd_path = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd_path.read_bytes()).hexdigest() == XSD_SHA256
    validation = XSDValidator(XSD_DIRECTORY).validate_xml(xml, xsd_path)
    assert validation["valid"], validation


def test_research_plan_keeps_cross_form_requirements_and_review_gates_open() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=True)
    evidence = json.loads((FORM_ROOT / "evidence.json").read_text())
    registrations = json.loads(REGISTRATIONS.read_text())

    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 13
    assert all(
        mapping["status"] == "proposed" for mapping in evidence["semanticReview"]["mappings"]
    )
    assert evidence["behaviorEvidence"] == []
    assert evidence["operationalBehaviorEvidence"] == []
    assert projected.form_rule_schema is not None
    assert all("gg_conditional" not in rule for rule in projected.form_rule_schema.values())

    resolved = build_preview_form(FORM_ID).form_json_schema["properties"]
    assert (
        "eligible resubmission or revision" in resolved["introduction"]["allOf"][0]["description"]
    )
    assert (
        "eligible renewal"
        in resolved["progress_report_publication_list"]["allOf"][0]["description"]
    )
    vertebrate_mapping = next(
        mapping
        for mapping in evidence["semanticReview"]["mappings"]
        if mapping["canonicalPointer"] == "#/properties/vertebrateAnimals"
    )
    assert "distinct" in vertebrate_mapping["note"]
    assert FORM_ID not in registrations["forms"]

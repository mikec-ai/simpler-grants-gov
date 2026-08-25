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
SCALAR_ATTACHMENTS = (
    ("introduction", "IntroductionToApplication", "11111111-1111-1111-1111-000000000001"),
    ("specific_aims", "SpecificAims", "11111111-1111-1111-1111-000000000002"),
    ("research_strategy", "ResearchStrategy", RESEARCH_STRATEGY_ID),
    (
        "progress_report_publication_list",
        "ProgressReportPublicationList",
        "11111111-1111-1111-1111-000000000004",
    ),
    ("vertebrate_animals", "VertebrateAnimals", "11111111-1111-1111-1111-000000000005"),
    ("select_agent_research", "SelectAgentResearch", "11111111-1111-1111-1111-000000000006"),
    (
        "multiple_pd_pi_leadership_plan",
        "MultiplePDPILeadershipPlan",
        "11111111-1111-1111-1111-000000000007",
    ),
    (
        "consortium_contractual_arrangements",
        "ConsortiumContractualArrangements",
        "11111111-1111-1111-1111-000000000008",
    ),
    ("letters_of_support", "LettersOfSupport", "11111111-1111-1111-1111-000000000009"),
    (
        "resource_sharing_plans",
        "ResourceSharingPlans",
        "11111111-1111-1111-1111-000000000010",
    ),
    ("other_plans", "OtherPlans", "11111111-1111-1111-1111-000000000011"),
    (
        "key_resource_authentication",
        "KeyBiologicalAndOrChemicalResources",
        "11111111-1111-1111-1111-000000000012",
    ),
)
SCALAR_IDS = tuple(attachment_id for _, _, attachment_id in SCALAR_ATTACHMENTS)
MINIMAL_RESPONSE = {"research_strategy": RESEARCH_STRATEGY_ID}
MAXIMUM_APPENDIX_RESPONSE = {
    **MINIMAL_RESPONSE,
    "appendix": list(APPENDIX_IDS),
}
ALL_ROLES_RESPONSE = {
    **{field: attachment_id for field, _, attachment_id in SCALAR_ATTACHMENTS},
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
    attachment_ids = (*SCALAR_IDS, *APPENDIX_IDS)

    assert _validation_fields({}) == {"$.research_strategy"}
    assert _validation_fields(ALL_ROLES_RESPONSE, attachment_ids=attachment_ids) == set()
    for field, _, attachment_id in SCALAR_ATTACHMENTS:
        known_ids = tuple(item for item in attachment_ids if item != attachment_id)
        assert _validation_fields(ALL_ROLES_RESPONSE, attachment_ids=known_ids) == {f"$.{field}"}
    for index, attachment_id in enumerate(APPENDIX_IDS):
        known_ids = tuple(item for item in attachment_ids if item != attachment_id)
        assert _validation_fields(ALL_ROLES_RESPONSE, attachment_ids=known_ids) == {
            f"$.appendix[{index}]"
        }
    assert _validation_fields(
        {**MINIMAL_RESPONSE, "appendix": [*APPENDIX_IDS, RESEARCH_STRATEGY_ID]},
        attachment_ids=attachment_ids,
    ) == {"$.appendix"}

    submitted = _application_form(ALL_ROLES_RESPONSE, attachment_ids=attachment_ids)
    assert validate_application_form(submitted, ApplicationAction.SUBMIT) == []
    assert submitted.application_form_status is ApplicationFormStatus.COMPLETE
    assert submitted.application_response == ALL_ROLES_RESPONSE
    assert json.loads(json.dumps(submitted.application_response, sort_keys=True)) == (
        ALL_ROLES_RESPONSE
    )


def test_research_plan_xml_flattens_appendix_and_validates_exact_official_xsd() -> None:
    attachment_ids = (*SCALAR_IDS, *APPENDIX_IDS)
    xml = _generate_xml(ALL_ROLES_RESPONSE, *attachment_ids)
    root = etree.fromstring(xml.encode())

    assert root.tag == f"{{{FORM_NAMESPACE}}}PHS398_ResearchPlan_5_0"
    assert root.get(f"{{{FORM_NAMESPACE}}}FormVersion") == "5.0"
    for index, (_, element, _) in enumerate(SCALAR_ATTACHMENTS, start=1):
        filenames = root.xpath(
            f"rp:ResearchPlanAttachments/rp:{element}/rp:attFile/att:FileName/text()",
            namespaces={"rp": FORM_NAMESPACE, "att": ATTACHMENT_NAMESPACE},
        )
        assert filenames == [f"document-{index}.pdf"]
    appendix_files = root.xpath(
        "rp:ResearchPlanAttachments/rp:Appendix/att:AttachedFile/att:FileName/text()",
        namespaces={"rp": FORM_NAMESPACE, "att": ATTACHMENT_NAMESPACE},
    )
    assert appendix_files == [f"document-{index}.pdf" for index in range(13, 23)]

    xsd_path = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd_path.read_bytes()).hexdigest() == XSD_SHA256
    xsd = etree.parse(xsd_path)
    appendix_declaration = xsd.xpath(
        "//xs:element[@name='Appendix']", namespaces={"xs": "http://www.w3.org/2001/XMLSchema"}
    )
    assert len(appendix_declaration) == 1
    assert appendix_declaration[0].get("type") == "att:AttachmentGroupMin0Max100DataType"
    attachments_xsd = XSD_DIRECTORY / "Attachments-V1.0.xsd"
    assert hashlib.sha256(attachments_xsd.read_bytes()).hexdigest() == (
        "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d"
    )
    attachments_schema = etree.parse(attachments_xsd)
    appendix_items = attachments_schema.xpath(
        "//xs:complexType[@name='AttachmentGroupMin0Max100DataType']"
        "/xs:sequence/xs:element[@name='AttachedFile']",
        namespaces={"xs": "http://www.w3.org/2001/XMLSchema"},
    )
    assert len(appendix_items) == 1
    assert appendix_items[0].get("maxOccurs") == "100"
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
    assert [
        (source["type"], source["uri"], source["sha256"]) for source in evidence["sources"]
    ] == [
        (
            "xsd",
            "https://apply07.grants.gov/apply/forms/schemas/PHS398_ResearchPlan_5_0-V5.0.xsd",
            XSD_SHA256,
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/Attachments-V1.0.xsd",
            "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/Global-V1.0.xsd",
            "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/GlobalLibrary-V2.0.xsd",
            "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/UniversalCodes-V2.0.xsd",
            "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
        ),
        (
            "dat",
            "https://apply07.grants.gov/apply/forms/sample/PHS398_ResearchPlan_5_0-V5.0_F797.xls",
            "61af459ba15e7a4ef5ddc4856a598561ce91bccb19f34084e977edb4eb4e7c88",
        ),
        (
            "pdf",
            "https://apply07.grants.gov/apply/forms/readonly/PHS398_ResearchPlan_5_0-V5.0.pdf",
            "1ae85b51a0502315b0370e596660c9c9518458152af3c15f1ef1c1d35638a12b",
        ),
        (
            "pdf",
            "https://apply07.grants.gov/apply/forms/sample/PHS398_ResearchPlan_5_0-V5.0.pdf",
            "587caf4945c63fd5070d28ae79d924d5a24c647231f8fdb32e17040b794b93db",
        ),
        (
            "instructions",
            "https://raw.githubusercontent.com/mikec-ai/grants-form-spec/main/research/"
            "phs398-research-plan/nih-forms-i-g400-instructions.json",
            "20531aa9715fe2a1f53eca4e38e684ac5c93c0ea7266e0a7ecc80852453af935",
        ),
    ]
    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "artifact": "artifacts/proof/grantsgov-PHS398ResearchPlan.jsonl.manifest.json",
        "sourceSetSha256": "b2373ff2a3f9e26a51a379c267e58329443cace14660b4fe4a66e14651614b01",
        "extractedAt": "2026-08-18T17:32:17.999441Z",
    }

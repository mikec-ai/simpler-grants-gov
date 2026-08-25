"""PHS 398 Cover Page Supplement technical handoff evidence.

The form remains an unregistered preview with proposed semantics. These checks
exercise its banked package through Simpler's generic preview and XML paths
without inventing source behaviors that are not compiled in the artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import xmlschema
from lxml import etree

from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form
from src.form_schema.form_spec.preview import build_preview_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo

FORM_ID = "phs398-cover-page-supplement"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID
FORM_NAMESPACE = "http://apply.grants.gov/forms/PHS398_CoverPageSupplement_5_0-V5.0"
GLOBAL_LIBRARY_NAMESPACE = "http://apply.grants.gov/system/GlobalLibrary-V2.0"
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
FORM_XSD = "PHS398_CoverPageSupplement_5_0-V5.0.xsd"
PROJECTED_UI_FIXTURE = (
    Path(__file__).parents[5]
    / "frontend/src/utils/applyForm/__fixtures__/phs398-cover-page-supplement-ui-schema.json"
)
PINNED_XSDS = {
    FORM_XSD: "ec538c9bb5fd233c36ac73ca567d31e60779ee3df2f3c7b456d9395b3ec2dc26",
    "Attachments-V1.0.xsd": "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
    "Global-V1.0.xsd": "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
    "GlobalLibrary-V2.0.xsd": "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
    "UniversalCodes-V2.0.xsd": "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
}
ASSURANCE_ID = "11111111-1111-1111-1111-111111111111"
CONSENT_ID = "22222222-2222-2222-2222-222222222222"
SOURCE_BOUND_UNCOMPILED = {
    ("B-1-1", "/programIncome/periods"),
    ("B-2-1", "/programIncome/periods"),
    ("B-2-2", "/programIncome/periods/[]/budgetPeriod"),
    ("B-2-3", "/programIncome/periods/[]/anticipatedAmount"),
    ("B-2-4", "/programIncome/periods/[]/source"),
    ("B-2-5", "/programIncome/periods"),
    ("C-3-2", "/humanEmbryonicStemCells/cellLines"),
    ("C-3-4", "/humanEmbryonicStemCells/cellLines"),
    ("E-1-1", "/inventionsAndPatents/inventions"),
    ("F-1-1", "/changes/changeOfProjectDirector"),
    ("F-2-1", "/changes/changeOfRecipientOrganization"),
    (
        "G.210 section 1, Are vertebrate animals euthanized?",
        "/vertebrateAnimals/animalEuthanized",
    ),
    (
        "G.210 section 2, Additional Instructions for Training and Multi-project",
        "/programIncome/anticipated",
    ),
    (
        "G.210 section 3, Additional Instructions for Multi-project",
        "/humanEmbryonicStemCells/involved",
    ),
    (
        "G.210 section 4, Additional Instructions for Multi-project",
        "/humanFetalTissue/involved",
    ),
    (
        "G.210 section 6, Change of Project Director/Principal Investigator",
        "/changes/changeOfProjectDirector",
    ),
    (
        "G.210 section 6, Change of Recipient Organization",
        "/changes/changeOfRecipientOrganization",
    ),
}


def read(relative: str):
    return json.loads((FORM_ROOT / relative).read_text())


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def attachment_mapping() -> dict[str, AttachmentInfo]:
    return {
        ASSURANCE_ID: AttachmentInfo(
            filename="HFTComplianceAssurance.pdf",
            mime_type="application/pdf",
            file_location="./attachments/HFTComplianceAssurance.pdf",
            hash_value="YWJjZA==",
        ),
        CONSENT_ID: AttachmentInfo(
            filename="HFTSampleIRBConsentForm.pdf",
            mime_type="application/pdf",
            file_location="./attachments/HFTSampleIRBConsentForm.pdf",
            hash_value="ZWZnaA==",
        ),
    }


def representative_response() -> dict[str, object]:
    return {
        "vertebrate_animals": {
            "animal_euthanized": "Y: Yes",
            "avma_consistent": "N: No",
            "method_description": "Scientific justification",
        },
        "program_income": {
            "anticipated": "Y: Yes",
            "periods": [
                {
                    "budget_period": 1,
                    "anticipated_amount": "12.34",
                    "source": "Licensing",
                }
            ],
        },
        "human_embryonic_stem_cells": {
            "involved": "Y: Yes",
            "specific_line_unavailable": "N: No",
            "cell_lines": ["0001", "0123"],
        },
        "human_fetal_tissue": {
            "involved": "Y: Yes",
            "compliance_assurance": ASSURANCE_ID,
            "irb_consent_form": CONSENT_ID,
        },
        "inventions_and_patents": {
            "inventions": "Y: Yes",
            "previously_reported": "N: No",
        },
        "changes": {
            "change_of_project_director": "Y: Yes",
            "change_of_recipient_organization": "Y: Yes",
        },
        "former_project_director": {
            "prefix": "Dr",
            "first_name": "Ada",
            "middle_name": "M",
            "last_name": "Lovelace",
            "suffix": "III",
        },
        "former_organization_name": "Former Research Institute",
    }


def attachment_rule_context(available_ids: tuple[str, ...]) -> JsonRuleContext:
    projected = _load_banked_form(FORM_ID, project_xml=False)
    application_form = cast(
        ApplicationForm,
        SimpleNamespace(
            application_response=representative_response(),
            application=SimpleNamespace(
                application_attachments=[
                    SimpleNamespace(application_attachment_id=attachment_id)
                    for attachment_id in available_ids
                ]
            ),
            application_form_id="phs398-cover-page-supplement-rule-test",
            form_id="phs398-cover-page-supplement-preview",
            form=projected,
        ),
    )
    context = JsonRuleContext(
        application_form,
        JsonRuleConfig(
            do_pre_population=False,
            do_post_population=False,
            do_field_validation=True,
        ),
    )
    process_rule_schema_for_context(context)
    return context


def test_cover_page_preview_preserves_compiled_conditions_and_open_gates() -> None:
    form = build_preview_form(FORM_ID)
    projected = _load_banked_form(FORM_ID, project_xml=False)
    evidence = read("evidence.json")
    conditionals = [
        node["conditional"]
        for node in walk(form.form_ui_schema)
        if isinstance(node, dict) and "conditional" in node
    ]

    assert form.form_name == "[Portable preview] PHS 398 Cover Page Supplement"
    assert form.form_version == "5.0"
    assert form.legacy_form_id == 698
    assert form.form_json_schema["required"] == [
        "program_income",
        "human_embryonic_stem_cells",
        "human_fetal_tissue",
    ]
    assert len(conditionals) == 13
    assert json.loads(PROJECTED_UI_FIXTURE.read_text()) == projected.form_ui_schema
    assert form.form_ui_schema == projected.form_ui_schema
    assert all(rule["then"] == {"interaction": "enabled"} for rule in conditionals)
    assert all(rule["otherwise"] == {"interaction": "disabled"} for rule in conditionals)

    behaviors = evidence["behaviorEvidence"]
    source_bound = {
        (row["sourcePath"], row["canonicalPath"])
        for row in behaviors
        if row["executionStatus"] == "source-bound-uncompiled"
    }
    assert len(source_bound) == 17
    assert source_bound == SOURCE_BOUND_UNCOMPILED
    hesc_unavailable = next(row for row in behaviors if row["sourcePath"] == "C-3-0")
    assert "automatic unchecking" in hesc_unavailable["sourceRecord"]
    assert "remains uncompiled" in hesc_unavailable["sourceRecord"]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert {row["status"] for row in evidence["semanticReview"]["mappings"]} == {"proposed"}


def test_cover_page_attachments_execute_through_shared_rule_processing() -> None:
    valid = attachment_rule_context((ASSURANCE_ID, CONSENT_ID))
    assert valid.attachment_ids == {ASSURANCE_ID, CONSENT_ID}
    assert valid.validation_issues == []

    for available, missing, expected_field in (
        ((ASSURANCE_ID,), CONSENT_ID, "$.human_fetal_tissue.irb_consent_form"),
        ((CONSENT_ID,), ASSURANCE_ID, "$.human_fetal_tissue.compliance_assurance"),
    ):
        context = attachment_rule_context(available)
        assert context.attachment_ids == {ASSURANCE_ID, CONSENT_ID}
        assert len(context.validation_issues) == 1
        issue = context.validation_issues[0]
        assert issue.field == expected_field
        assert issue.value == missing


def test_cover_page_emits_exact_source_valid_xml_through_generic_service() -> None:
    context = attachment_rule_context((ASSURANCE_ID, CONSENT_ID))
    assert context.attachment_ids == {ASSURANCE_ID, CONSENT_ID}
    assert context.validation_issues == []
    projected = _load_banked_form(FORM_ID, project_xml=True)
    assert projected.json_to_xml_schema is not None
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=cast(dict[str, Any], context.json_data),
            transform_config=projected.json_to_xml_schema,
            attachment_mapping=attachment_mapping(),
        )
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None

    locations: dict[str, str] = {}
    for filename, digest in PINNED_XSDS.items():
        path = XSD_DIRECTORY / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        namespace = etree.parse(path).getroot().get("targetNamespace")
        assert namespace is not None
        locations[namespace] = str(path.resolve())
    schema = xmlschema.XMLSchema(
        str((XSD_DIRECTORY / FORM_XSD).resolve()), locations=locations, allow="local"
    )
    errors = list(schema.iter_errors(generated.xml_data))
    assert not errors, "\n".join(str(error) for error in errors)

    root = etree.fromstring(generated.xml_data.encode())

    def q(name: str) -> str:
        return f"{{{FORM_NAMESPACE}}}{name}"

    assert root.tag == q("PHS398_CoverPageSupplement_5_0")
    assert root.get(q("FormVersion")) == "5.0"
    assert [node.text for node in root.findall(q("IncomeBudgetPeriod") + "/" + q("Source"))] == [
        "Licensing"
    ]
    assert [node.text for node in root.findall(q("StemCells") + "/" + q("CellLines"))] == [
        "0001",
        "0123",
    ]
    former = root.find(q("FormerPD_Name"))
    assert former is not None
    assert former.findtext(f"{{{GLOBAL_LIBRARY_NAMESPACE}}}FirstName") == "Ada"
    assert root.findtext(q("FormerInstitutionName")) == "Former Research Institute"


def test_cover_page_remains_unregistered_with_proposed_semantics() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())
    evidence = read("evidence.json")

    assert FORM_ID not in registrations["forms"]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert not (ARTIFACTS.parent / "projections" / f"{FORM_ID}.json").exists()

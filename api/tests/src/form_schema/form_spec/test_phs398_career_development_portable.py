"""PHS 398 Career Development is a reuse, condition, and XML canary."""

import hashlib
import json
from pathlib import Path

import xmlschema
from lxml import etree

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo

FORM_ID = "phs398-career-development-supplemental"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
FORM_XSD = "PHS398_CareerDevelopmentAwardSup_6_0-V6.0.xsd"
FORM_XSD_SHA256 = "613641fc799a5c92d47928c98ebd90fad5d348b7637005929f0c0dc4a07e95c1"
PINNED_XSDS = {
    FORM_XSD: FORM_XSD_SHA256,
    "Attachments-V1.0.xsd": "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
    "Global-V1.0.xsd": "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
    "GlobalLibrary-V2.0.xsd": "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
    "UniversalCodes-V2.0.xsd": "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
}


def test_career_development_loads_without_form_specific_adapter_code() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=True)

    assert projected.meta == {
        "id": FORM_ID,
        "legacyFormId": 799,
        "formName": "PHS 398 Career Development Award Supplemental Form",
        "shortFormName": "PHS398_CareerDevelopmentAwardSup_6_0",
        "formVersion": "6.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "0925-0001",
    }
    assert len(projected.form_json_schema["properties"]) == 20
    assert projected.form_json_schema["required"] == ["research_strategy", "citizenship"]
    assert len(projected.form_rule_schema or {}) == 19
    assert projected.json_to_xml_schema is not None


def test_career_development_preserves_provenance_and_open_semantic_review() -> None:
    evidence = json.loads((FORM_ROOT / "evidence.json").read_text())
    sources = {source["id"]: source for source in evidence["sources"]}

    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 12
    assert sources["phs398-career-development-xsd-v6-0"]["sha256"] == FORM_XSD_SHA256
    assert sources["phs398-career-development-dat-f799"]["sha256"] == (
        "be709f9d3e28537c79593527673f1af5fbc40c32664f6521256336116671318e"
    )
    compiled = {
        row["canonicalPath"]
        for row in evidence["behaviorEvidence"]
        if row["executionStatus"] == "compiled"
    }
    assert compiled == {
        "citizenship.nonUsCitizenStatus",
        "citizenship.permanentResidentByAward",
    }


def test_career_development_emits_source_valid_xml_through_generic_service() -> None:
    attachment_id = "11111111-1111-1111-1111-111111111111"
    projected = _load_banked_form(FORM_ID, project_xml=True)
    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={
                "research_strategy": attachment_id,
                "citizenship": {"us_citizen_or_national": "Y: Yes"},
            },
            transform_config=projected.json_to_xml_schema,
            attachment_mapping={
                attachment_id: AttachmentInfo(
                    filename="strategy.pdf",
                    mime_type="application/pdf",
                    file_location="./attachments/strategy.pdf",
                    hash_value="YWJj",
                )
            },
        )
    )
    assert response.success, response.error_message
    assert response.xml_data is not None

    locations: dict[str, str] = {}
    for filename, digest in PINNED_XSDS.items():
        path = XSD_DIRECTORY / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        namespace = etree.parse(path).getroot().get("targetNamespace")
        assert namespace is not None
        locations[namespace] = str(path.resolve())
    xsd_path = XSD_DIRECTORY / FORM_XSD
    schema = xmlschema.XMLSchema(str(xsd_path.resolve()), locations=locations, allow="local")
    errors = list(schema.iter_errors(response.xml_data))
    assert not errors, "\n".join(str(error) for error in errors)

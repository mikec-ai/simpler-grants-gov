import hashlib
import json
from pathlib import Path

import xmlschema
from lxml import etree

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService

FORM = ARTIFACTS / "forms" / "nifa-supplemental"
FORM_ID = "nifa-supplemental"
FORM_NAMESPACE = "http://apply.grants.gov/forms/NIFA_Supplemental_Info_1_2-V1.2"
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
FORM_XSD = "NIFA_Supplemental_Info_1_2-V1.2.xsd"
PINNED_XSDS = {
    FORM_XSD: "9fd2d43797ec5fe17a9c29f073295e1c459b13d39346b3422de036d51c1d69e2",
    "Attachments-V1.0.xsd": "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
    "Global-V1.0.xsd": "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
    "GlobalLibrary-V2.0.xsd": "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
    "UniversalCodes-V2.0.xsd": "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
}


def read(relative: str):
    return json.loads((FORM / relative).read_text())


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_nifa_package_is_banked_with_portable_behavior_and_provenance() -> None:
    manifest = read("manifest.json")
    schema = read("schema.json")
    ui = read("sgg/ui-schema.json")
    evidence = read("evidence.json")

    assert manifest["form"]["legacyFormId"] == 483
    assert manifest["form"]["formVersion"] == "1.2"
    assert schema["required"] == [
        "fundingOpportunity",
        "program",
        "applicantType",
        "asapRecipientInformation",
        "keywords",
    ]
    additional = next(
        node
        for node in walk(ui)
        if node.get("definition", "").endswith(
            "/additionalApplicantType/properties/additionalApplicantType"
        )
    )
    assert additional["conditional"]["when"] == {
        "op": "in",
        "ref": {"scope": "root", "pointer": "/applicantType/applicantTypeCode"},
        "values": [
            "H: Public/state Controlled Institution of Higher Education",
            "X: Other (specify)",
        ],
    }
    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 22
    assert not any(row["status"] == "accepted" for row in evidence["semanticReview"]["mappings"])


def test_nifa_xml_profile_is_generic_and_uses_the_exact_official_xsd() -> None:
    profile = read("targets/grants-gov-xml.json")
    xsd = Path("src/services/xml_generation/xsds/NIFA_Supplemental_Info_1_2-V1.2.xsd")

    assert (
        profile["xsd"]["sha256"]
        == "9fd2d43797ec5fe17a9c29f073295e1c459b13d39346b3422de036d51c1d69e2"
    )
    assert xsd.is_file()
    assert profile["mapping"]["fields"]["applicantType"]["source"] == (
        "/applicantType/applicantTypeCode"
    )
    assert profile["mapping"]["fields"]["asapRecipientInformation"]["fields"][
        "hasActiveAsapRecipientId"
    ]["valueMap"] == {"true": "Y: Yes", "false": "N: No"}
    assert not Path("src/form_schema/form_spec/projections/nifa-supplemental.json").exists()


def test_nifa_emits_source_valid_xml_through_the_generic_service() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=True)
    assert projected.json_to_xml_schema is not None
    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={
                "funding_opportunity": {
                    "title": "NIFA Research Opportunity",
                    "number": "USDA-NIFA-TEST-001",
                },
                "program": {
                    "program_code_name": "Agriculture Research",
                    "program_code": "AR01",
                },
                "applicant_type": {
                    "applicant_type_code": (
                        "H: Public/state Controlled Institution of Higher Education"
                    )
                },
                "additional_applicant_type": {
                    "additional_applicant_type": "1862 Land-Grant University"
                },
                "supplemental_applicant_types": {
                    "cooperative_extension_service": True,
                    "veterinary_school_or_college": False,
                },
                "asap_recipient_information": {
                    "has_active_asap_recipient_id": True,
                    "recipient_id": "12345678",
                },
                "keywords": "agriculture, extension",
            },
            transform_config=projected.json_to_xml_schema,
            attachment_mapping={},
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
    schema = xmlschema.XMLSchema(
        str((XSD_DIRECTORY / FORM_XSD).resolve()), locations=locations, allow="local"
    )
    errors = list(schema.iter_errors(response.xml_data))
    assert not errors, "\n".join(str(error) for error in errors)

    root = etree.fromstring(response.xml_data.encode())

    def q(name: str) -> str:
        return f"{{{FORM_NAMESPACE}}}{name}"

    assert root.get(q("FormVersion")) == "1.2"
    assert root.findtext(f"{q('FundingOpportunity')}/{q('FundingOpportunityTitle')}") == (
        "NIFA Research Opportunity"
    )
    assert root.findtext(q("ApplicantTypeCode")) == (
        "H: Public/state Controlled Institution of Higher Education"
    )
    assert root.findtext(f"{q('ASAP_Recipient_Info')}/{q('ASAPID')}") == "Y: Yes"
    assert root.findtext(f"{q('ASAP_Recipient_Info')}/{q('RecipientID')}") == "12345678"
    supplemental = root.find(q("SupplementalApplicantType"))
    assert supplemental is not None
    assert supplemental.findtext(q("CooperativeExtensionService")) == "Y: Yes"
    assert supplemental.findtext(q("VeterinarySchoolorCollege")) == "N: No"


def test_nifa_remains_unregistered_with_semantics_proposed() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())
    evidence = read("evidence.json")

    assert FORM_ID not in registrations["forms"]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert {mapping["status"] for mapping in evidence["semanticReview"]["mappings"]} == {"proposed"}

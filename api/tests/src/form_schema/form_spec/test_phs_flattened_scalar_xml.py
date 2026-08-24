"""Pinned-XSD proofs for portable flattened scalar-array mappings in Simpler."""

import hashlib
from pathlib import Path

import xmlschema
from lxml import etree

from src.form_schema.form_spec.loader import _load_banked_form
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo

XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
PINNED_XSDS = {
    "PHSInclusionEnrollmentReport-V1.0.xsd": "3263bbfa8881c7d428958cf91de470cd19f0f6cbc11818c4752d5266bb0f53a4",
    "PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0.xsd": "29d859de80cc9febbd1599c28f5db9a3ec82bff26a4d32f4dbbc372effb56bf3",
    "HumanSubjectStudy_3_0-V3.0.xsd": "799205dea5eddcf13f926cc39d5fc7de27c6a6cdcc68eff4d49e1b629d4351cf",
    "Attachments-V1.0.xsd": "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
    "Global-V1.0.xsd": "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
    "GlobalLibrary-V2.0.xsd": "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
    "UniversalCodes-V2.0.xsd": "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
}


def _generate(
    form_id: str,
    data: dict[str, object],
    attachments: dict[str, AttachmentInfo] | None = None,
) -> str:
    profile = _load_banked_form(form_id).json_to_xml_schema
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


def _assert_pinned_xsd(xml: str, filename: str) -> etree._Element:
    locations: dict[str, str] = {}
    for pinned_filename, digest in PINNED_XSDS.items():
        path = XSD_DIRECTORY / pinned_filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        namespace = etree.parse(path).getroot().get("targetNamespace")
        assert namespace is not None
        locations[namespace] = str(path.resolve())

    # ``allow="local"`` makes the proof fail if the complete pinned closure cannot
    # resolve locally; an imported schema may never be fetched from Grants.gov.
    schema = xmlschema.XMLSchema(
        str((XSD_DIRECTORY / filename).resolve()),
        locations=locations,
        allow="local",
    )
    errors = list(schema.iter_errors(xml))
    assert not errors, "\n".join(str(error) for error in errors)
    return etree.fromstring(xml.encode())


def _report() -> dict[str, object]:
    return {
        "title": "Enrollment report",
        "uses_existing_dataset_or_resource": "N: No",
        "location_type": "Domestic",
        "enrollment_countries": ["USA: UNITED STATES", "CAN: CANADA"],
    }


def test_inclusion_report_repeats_country_elements_and_validates_exact_xsd() -> None:
    xml = _generate("phs-inclusion-enrollment-report", {"reports": [_report()]})
    root = _assert_pinned_xsd(
        xml,
        "PHSInclusionEnrollmentReport-V1.0.xsd",
    )
    namespace = "http://apply.grants.gov/forms/PHSInclusionEnrollmentReport-V1.0"
    countries = root.findall(f".//{{{namespace}}}EnrollmentCountry")
    assert [country.text for country in countries] == [
        "USA: UNITED STATES",
        "CAN: CANADA",
    ]


def test_human_subjects_nested_report_repeats_countries_and_validates_exact_xsd() -> None:
    attachment_id = "11111111-1111-1111-1111-111111111111"
    study = {
        "study_title": "Structured study",
        "exempt_from_federal_regulations": "N: No",
        "clinical_trial_questionnaire": {
            "human_participants": "Y: Yes",
            "prospectively_assigned_intervention": "Y: Yes",
            "evaluates_intervention": "Y: Yes",
            "health_related_outcome": "Y: Yes",
        },
        "population_characteristics": {"inclusion_enrollment_reports": [_report()]},
        "other_clinical_trial_attachments": [attachment_id],
    }
    xml = _generate(
        "phs-human-subjects",
        {
            "involves_human_specimens_or_data": "N: No",
            "involves_human_subjects": "Y: Yes",
            "studies": [study],
        },
        {
            attachment_id: AttachmentInfo(
                filename="clinical-trial.pdf",
                mime_type="application/pdf",
                file_location="./attachments/clinical-trial.pdf",
                hash_value="YWJj",
            )
        },
    )
    root = _assert_pinned_xsd(
        xml,
        "PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0.xsd",
    )
    namespace = "http://apply.grants.gov/forms/HumanSubjectStudy_3_0-V3.0"
    countries = root.findall(f".//{{{namespace}}}EnrollmentCountry")
    assert [country.text for country in countries] == [
        "USA: UNITED STATES",
        "CAN: CANADA",
    ]
    attachment_namespace = "http://apply.grants.gov/system/Attachments-V1.0"
    files = root.findall(f".//{{{attachment_namespace}}}AttachedFile")
    assert len(files) == 1
    assert files[0].find(f"{{{attachment_namespace}}}FileName").text == "clinical-trial.pdf"

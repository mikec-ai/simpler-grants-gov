"""R&R SF-424 XML conformance from the portable source-bound target."""

from pathlib import Path

from lxml import etree

from src.form_schema.form_spec.loader import load_form
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.lifecycle import submit_form
from tests.src.form_schema.form_spec.test_rr_sf424_portable import VALID_RESPONSE

XSD_DIRECTORY = Path("src/services/xml_generation/xsds")
FORM_NAMESPACE = "http://apply.grants.gov/forms/RR_SF424_5_0-V5.0"


def _generate_xml() -> str:
    form = load_form("rr-sf424")
    assert form.json_to_xml_schema is not None
    submitted = submit_form("rr-sf424", VALID_RESPONSE)
    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=submitted.application_response,
            transform_config=form.json_to_xml_schema,
            attachment_mapping={},
        )
    )
    assert response.success, response.error_message
    assert response.xml_data is not None
    return response.xml_data


def test_rr_sf424_wire_only_congressional_district_group_is_emitted() -> None:
    root = etree.fromstring(_generate_xml().encode())

    district = root.find(f"{{{FORM_NAMESPACE}}}CongressionalDistrict")
    assert district is not None
    applicant = district.find(f"{{{FORM_NAMESPACE}}}ApplicantCongressionalDistrict")
    assert applicant is not None
    assert applicant.text == "MD-008"


def test_rr_sf424_representative_submission_validates_against_pinned_xsd() -> None:
    result = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(_generate_xml(), "RR_SF424_5_0-V5.0")

    assert result["valid"], result

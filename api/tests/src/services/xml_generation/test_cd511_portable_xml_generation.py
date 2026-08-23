"""CD-511 XML conformance from the pinned portable producer declaration."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator
from lxml import etree

from src.form_schema.form_spec.loader import load_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.test_cd511_portable import VALID_RESPONSE


XSD_DIRECTORY = Path("src/services/xml_generation/xsds")
XSD_NAME = "CD511-V1.1.xsd"
FORM_NS = "http://apply.grants.gov/forms/CD511-V1.1"
GLOB_LIB_NS = "http://apply.grants.gov/system/GlobalLibrary-V2.0"
XSD_SHA256 = "f13c05b8e62fe1e7cf0198053f79fdd34efe4b7d10b56974d27a7dd45d013fde"


def _generate_xml() -> str:
    response = copy.deepcopy(VALID_RESPONSE)
    response.update({
        "award_number": "AWARD-123",
        "signature": "reviewer@example.gov",
        "submitted_date": "2026-08-23",
    })
    form = load_form("cd511")
    schema = resolve_jsonschema(copy.deepcopy(form.form_json_schema))
    assert list(Draft202012Validator(schema).iter_errors(response)) == []
    assert form.json_to_xml_schema is not None
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=form.json_to_xml_schema,
            attachment_mapping={},
        )
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    return generated.xml_data


def test_cd511_wire_shape_uses_the_portable_profile_without_adapter_exceptions() -> None:
    root = etree.fromstring(_generate_xml().encode())

    def q(name: str) -> str:
        return f"{{{FORM_NS}}}{name}"

    assert root.get(q("FormVersion")) == "1.1"
    assert root.findtext(q("OrganizationName")) == "Example Research Institute"
    assert root.findtext(q("AwardNumber")) == "AWARD-123"
    contact = root.find(q("ContactName"))
    assert contact is not None
    assert contact.findtext(f"{{{GLOB_LIB_NS}}}FirstName") == "Ada"
    assert contact.findtext(f"{{{GLOB_LIB_NS}}}LastName") == "Lovelace"


def test_cd511_representative_submission_validates_against_pinned_xsd() -> None:
    assert hashlib.sha256((XSD_DIRECTORY / XSD_NAME).read_bytes()).hexdigest() == XSD_SHA256
    result = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        _generate_xml(), XSD_NAME.removesuffix(".xsd")
    )

    assert result["valid"], result

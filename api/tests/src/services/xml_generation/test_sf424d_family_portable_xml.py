"""SF-424D family XML conformance from pinned portable producer profiles."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from lxml import etree

from src.form_schema.form_spec.loader import load_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.test_sf424d_portable import VALID_RESPONSE

XSD_DIRECTORY = Path("src/services/xml_generation/xsds")
PROFILES = {
    "sf424d": {
        "xsd": "SF424D-V1.1.xsd",
        "sha256": "22026ea7130a01b8674e1c3ce1668e1b57d5be65498b5a76042eb80d38de77f1",
        "namespace": "http://apply.grants.gov/forms/SF424D-V1.1",
        "versionChild": True,
    },
    "mandatory-sf424d": {
        "xsd": "Mandatory_SF424D-V1.1.xsd",
        "sha256": "6685f2c19329db0ee959e2453cbcaf749e9bb2d7f45cb96892d9a4e71d87f68d",
        "namespace": "http://apply.grants.gov/forms/Mandatory_SF424D-V1.1",
        "versionChild": False,
    },
    "individual-sf424d": {
        "xsd": "Individual_SF424D-V1.1.xsd",
        "sha256": "52187d42b9ca30cf1f2f95de50be13bbd9ae333ede4b843e8c43b23db4489356",
        "namespace": "http://apply.grants.gov/forms/Individual_SF424D-V1.1",
        "versionChild": False,
    },
}
GLOB_NS = "http://apply.grants.gov/system/Global-V1.0"


def _generate_xml(form_id: str) -> str:
    response = copy.deepcopy(VALID_RESPONSE)
    response.update({"signature": "Alex Authorized", "date_signed": "2026-08-23"})
    form = load_form(form_id)
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


@pytest.mark.parametrize("form_id", PROFILES)
def test_sf424d_profile_wire_shape_is_entirely_profile_driven(form_id: str) -> None:
    declaration = PROFILES[form_id]
    root = etree.fromstring(_generate_xml(form_id).encode())
    namespace = declaration["namespace"]

    def q(name: str) -> str:
        return f"{{{namespace}}}{name}"

    assert root.tag == q("Assurances")
    assert root.get(q("programType")) == "Construction"
    representative = root.find(q("AuthorizedRepresentative"))
    assert representative is not None
    assert representative.findtext(q("RepresentativeName")) == "Alex Authorized"
    assert representative.findtext(q("RepresentativeTitle")) == "Executive Director"
    assert root.findtext(q("ApplicantOrganizationName")) == "Example Research Organization"
    assert root.findtext(q("SubmittedDate")) == "2026-08-23"

    if declaration["versionChild"]:
        assert root.findtext(f"{{{GLOB_NS}}}FormVersionIdentifier") == "1.1"
        assert root.get(f"{{{GLOB_NS}}}coreSchemaVersion") == "1.1"
    else:
        assert root.find(f"{{{GLOB_NS}}}FormVersionIdentifier") is None
        assert root.get(q("FormVersion")) == "1.1"


@pytest.mark.parametrize("form_id", PROFILES)
def test_sf424d_profile_validates_against_exact_pinned_official_xsd(form_id: str) -> None:
    declaration = PROFILES[form_id]
    xsd = XSD_DIRECTORY / declaration["xsd"]
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == declaration["sha256"]
    result = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        _generate_xml(form_id), declaration["xsd"].removesuffix(".xsd")
    )

    assert result["valid"], result

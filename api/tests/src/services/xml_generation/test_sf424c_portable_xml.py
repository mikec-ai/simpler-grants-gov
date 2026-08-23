"""Exact-XSD XML canary for the promoted portable SF-424C package."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lxml import etree

from src.form_schema.form_spec.loader import load_form
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.test_sf424c_portable import calculated_response

XSD_DIRECTORY = Path("src/services/xml_generation/xsds")
XSD_NAME = "SF424C_2_0-V2.0.xsd"
XSD_SHA256 = "a3ec5d6bae8173fce080709a8071787293dbe6271415d905d230c584c200982a"
NAMESPACE = "http://apply.grants.gov/forms/SF424C_2_0-V2.0"


def _xml() -> str:
    form = load_form("sf424c")
    assert form.json_to_xml_schema is not None
    result = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=calculated_response(),
            transform_config=form.json_to_xml_schema,
            attachment_mapping={},
        )
    )
    assert result.success, result.error_message
    assert result.xml_data is not None
    return result.xml_data


def test_portable_profile_generates_the_declared_wire_shape() -> None:
    root = etree.fromstring(_xml().encode())

    assert root.tag == f"{{{NAMESPACE}}}SF424C_2_0"
    assert root.get(f"{{{NAMESPACE}}}programType") == "Construction"
    assert root.get(f"{{{NAMESPACE}}}FormVersion") == "2.0"
    assert root.findtext(f"{{{NAMESPACE}}}FederalFundingPercentageShareValue") == "80"
    assert root.findtext(f"{{{NAMESPACE}}}FederalFundingShareValue") == "824000.00"


def test_portable_xml_validates_against_the_exact_official_xsd() -> None:
    xsd = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == XSD_SHA256
    result = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        _xml(), XSD_NAME.removesuffix(".xsd")
    )

    assert result["valid"], result

"""SF-LLL XML conformance from the pinned portable producer declaration."""

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
from tests.src.form_schema.form_spec.test_sflll_portable import VALID_RESPONSE


XSD_DIRECTORY = Path("src/services/xml_generation/xsds")
XSD_NAME = "SFLLL_2_0-V2.0.xsd"
FORM_NS = "http://apply.grants.gov/forms/SFLLL_2_0-V2.0"
XSD_SHA256 = "fff7449d00c715efb79d83b572bc7b1ef3e8171f6a9ba841436b26242e883664"


def _response() -> dict:
    response = copy.deepcopy(VALID_RESPONSE)
    response.update({
        "report_type": "MaterialChange",
        "material_change": {
            "year": "2026",
            "quarter": "2",
            "last_report_date": "2026-04-01",
        },
        "reporting_entity_type": "SubAwardee",
        "tier": 0,
        "prime_organization": {
            "organization_name": "Prime Research Institute",
            "address": {
                "street1": "3 Research Way",
                "city": "Washington",
                "state": "DC: District of Columbia",
                "zip_code": "20001",
            },
            "congressional_district": "DC-000",
        },
        "individuals_performing_services": [
            {
                "name": {"first_name": "Grace", "last_name": "Hopper"},
                "address": {
                    "street1": "4 Research Way",
                    "city": "Arlington",
                    "state": "VA: Virginia",
                    "zip_code": "22201",
                },
            },
            {"name": {"first_name": "Katherine", "last_name": "Johnson"}},
        ],
    })
    response["signature_block"].update({
        "signed_date": "2026-08-23",
        "signature": "reviewer@example.gov",
    })
    return response


def _generate_xml() -> str:
    response = _response()
    form = load_form("sflll")
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


def test_sflll_wire_shape_preserves_attributes_roles_and_repeated_people() -> None:
    root = etree.fromstring(_generate_xml().encode())

    def q(name: str) -> str:
        return f"{{{FORM_NS}}}{name}"

    assert root.get(q("FormVersion")) == "2.0"
    supplement = root.find(q("MaterialChangeSupplement"))
    assert supplement is not None
    assert supplement.get(q("ReportType")) == "MaterialChange"

    report_entity = root.find(q("ReportEntity"))
    assert report_entity is not None
    assert report_entity.get(q("ReportEntityType")) == "SubAwardee"
    assert report_entity.findtext(q("ReportEntityIsPrime")) == "N: No"
    assert report_entity.find(q("ReportingEntity")).findtext(q("EntityType")) == "SubAwardee"
    assert report_entity.find(q("PrimeIfSubawardee")).findtext(q("EntityType")) == "Prime"
    tier = report_entity.find(q("Tier"))
    assert tier is not None
    assert tier.get(q("ReportEntityType")) == "SubAwardee"
    assert tier.findtext(q("TierValue")) == "0"

    people = root.find(q("IndividualsPerformingServices"))
    assert people is not None
    assert len(people.findall(q("Individual"))) == 2


def test_sflll_representative_submission_validates_against_pinned_xsd() -> None:
    assert hashlib.sha256((XSD_DIRECTORY / XSD_NAME).read_bytes()).hexdigest() == XSD_SHA256
    result = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        _generate_xml(), XSD_NAME.removesuffix(".xsd")
    )

    assert result["valid"], result

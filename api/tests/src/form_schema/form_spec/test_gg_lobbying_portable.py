"""Portable Grants.gov Lobbying v1.1 parity against the existing SGG oracle."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import freezegun
from lxml import etree as lxml_etree

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.forms.gg_lobbying_form import FORM_UI_SCHEMA as LEGACY_UI_SCHEMA
from src.form_schema.forms.gg_lobbying_form import FORM_XML_TRANSFORM_RULES as LEGACY_XML_RULES
from src.form_schema.forms.gg_lobbying_form import GG_LobbyingForm_v1_1
from src.form_schema.jsonschema_validator import validate_json_schema_for_form
from src.services.applications.application_validation import (
    ApplicationAction,
    validate_application_form,
)
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    application_form_for,
    assert_json_round_trip,
    assert_validation_case,
)
from tests.src.form_schema.forms.conftest import setup_resolved_form

VALID_RESPONSE = {
    "organization_name": "Example Research Organization",
    "authorized_representative_name": {
        "prefix": "Dr.",
        "first_name": "Ada",
        "middle_name": "M",
        "last_name": "Lovelace",
        "suffix": "PhD",
    },
    "authorized_representative_title": "Director",
}


def _xml(config: dict[str, object], response: dict[str, object]) -> bytes:
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(application_data=response, transform_config=config)
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    return generated.xml_data.encode()


def _canonical_xml(xml: bytes) -> bytes:
    return lxml_etree.tostring(lxml_etree.fromstring(xml), method="c14n")


def test_gg_lobbying_loads_as_a_distinct_certification_profile() -> None:
    projected = load_form("gg-lobbying")
    policy = json.loads((ARTIFACTS / "forms/gg-lobbying/policy-content.json").read_text())
    binding = json.loads((ARTIFACTS / "forms/gg-lobbying/policy-binding.json").read_text())

    assert projected.meta == {
        "id": "gg-lobbying",
        "legacyFormId": 255,
        "formName": "Grants.gov Lobbying Form",
        "shortFormName": "GG_LobbyingForm",
        "formVersion": "1.1",
        "agencyCode": "SGG",
        "ombNumber": "4040-0013",
    }
    assert set(projected.form_json_schema["properties"]) == {
        "organization_name",
        "authorized_representative_name",
        "authorized_representative_title",
        "authorized_representative_signature",
        "submitted_date",
    }
    assert projected.form_json_schema["required"] == [
        "organization_name",
        "authorized_representative_name",
        "authorized_representative_title",
    ]
    assert projected.meta["id"] != "sflll"
    assert policy["contract"] == "policy-content/v1"
    assert policy["id"] == "grants-gov/lobbying-certification"
    assert policy["kind"] == "certification"
    assert binding["contract"] == "form-policy-binding/v1"
    assert binding["policy"] == {"id": policy["id"], "version": policy["version"]}
    assert binding["acceptance"]["attestsTo"] == ["certification"]


def test_gg_lobbying_preserves_the_legacy_browser_and_print_input() -> None:
    portable = load_form("gg-lobbying").form_ui_schema

    # TypeSpec doc comments deliberately normalize the final newline; every rendered byte of
    # the legal text and every field/section identifier otherwise remains the legacy oracle.
    assert portable[0]["description"].rstrip() == LEGACY_UI_SCHEMA[0]["description"].rstrip()
    portable_without_description = copy.deepcopy(portable)
    legacy_without_description = copy.deepcopy(LEGACY_UI_SCHEMA)
    portable_without_description[0].pop("description")
    legacy_without_description[0].pop("description")
    assert portable_without_description == legacy_without_description


def test_gg_lobbying_complete_and_missing_certifying_identity_match_the_oracle() -> None:
    legacy = setup_resolved_form(GG_LobbyingForm_v1_1)

    vectors = [
        (VALID_RESPONSE, set()),
        (
            {},
            {
                "$.organization_name",
                "$.authorized_representative_name",
                "$.authorized_representative_title",
            },
        ),
        (
            {**VALID_RESPONSE, "authorized_representative_name": {}},
            {
                "$.authorized_representative_name.first_name",
                "$.authorized_representative_name.last_name",
            },
        ),
    ]
    for response, expected in vectors:
        assert_validation_case(
            "gg-lobbying",
            ValidationCase("portable parity vector", response, frozenset(expected)),
        )
        legacy_errors = validate_json_schema_for_form(response, legacy)
        assert {issue.field for issue in legacy_errors} == expected


@freezegun.freeze_time("2026-08-23 12:00:00", tz_offset=0)
def test_gg_lobbying_signature_date_and_application_context_match_the_oracle() -> None:
    legacy = setup_resolved_form(GG_LobbyingForm_v1_1)
    portable_application = application_form_for(
        "gg-lobbying", VALID_RESPONSE, submitter_email="reviewer@example.gov"
    )
    legacy_application = copy.deepcopy(portable_application)
    legacy_application.form = legacy
    legacy_application.form_id = legacy.form_id

    responses = []
    for application_form in (portable_application, legacy_application):
        assert validate_application_form(application_form, ApplicationAction.SUBMIT) == []
        responses.append(application_form.application_response)

    assert (
        responses[0]
        == responses[1]
        == {
            **VALID_RESPONSE,
            "authorized_representative_signature": "reviewer@example.gov",
            "submitted_date": "2026-08-23",
        }
    )
    assert_json_round_trip(responses[0])


def test_gg_lobbying_xml_matches_the_legacy_oracle_and_exact_xsd() -> None:
    response = {
        **VALID_RESPONSE,
        "authorized_representative_signature": "Ada Lovelace",
        "submitted_date": "2026-08-23",
    }
    portable_rules = load_form("gg-lobbying").json_to_xml_schema
    assert portable_rules is not None
    portable_xml = _xml(portable_rules, response)
    legacy_xml = _xml(LEGACY_XML_RULES, response)

    assert _canonical_xml(portable_xml) == _canonical_xml(legacy_xml)
    xsd_dir = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
    validation = XSDValidator(xsd_dir).validate_xml(
        portable_xml.decode(), xsd_dir / "GG_LobbyingForm-V1.1.xsd"
    )
    assert validation["valid"], validation["error_message"]


def test_gg_lobbying_evidence_pins_official_sources_and_legacy_oracle() -> None:
    evidence = json.loads((ARTIFACTS / "forms/gg-lobbying/evidence.json").read_text())
    sources = {source["id"]: source for source in evidence["sources"]}

    assert sources["grantsgov-gg-lobbying-xsd-1.1"]["sha256"] == (
        "a41d88b19e240dbb5f9b13815c0426d2396414fc1af8d6ab6a96f35855a0a5f7"
    )
    oracle = sources["sgg-legacy-gg-lobbying-oracle-30dd50cf"]
    assert oracle["nativeVersion"] == "30dd50cf0493146c32f89f78398979523e040080"
    assert oracle["sha256"] == ("bdf73a05a75b5020218f06864118f4c1e9ccc396934feaccc49e9acbbe406ad8")
    assert evidence["semanticReview"]["status"] == "proposed"


def test_gg_lobbying_canary_is_not_registered_before_release_review() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())

    assert "gg-lobbying" not in registrations["forms"]

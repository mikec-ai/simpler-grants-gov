"""Portable Grants.gov Lobbying v1.1 parity against the existing SGG oracle."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import freezegun
import pytest
from lxml import etree as lxml_etree

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.browser_plan import build_browser_plan
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
    assert binding["release"]["status"] == "draft"


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
    xsd = xsd_dir / "GG_LobbyingForm-V1.1.xsd"
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == (
        "a41d88b19e240dbb5f9b13815c0426d2396414fc1af8d6ab6a96f35855a0a5f7"
    )
    validation = XSDValidator(xsd_dir).validate_xml(portable_xml.decode(), xsd)
    assert validation["valid"], validation["error_message"]


def test_gg_lobbying_browser_plan_preserves_policy_without_accepting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ENABLE_PORTABLE_FORM_PREVIEW", "true")
    monkeypatch.setenv("PORTABLE_BROWSER_FORM_IDS", "gg-lobbying")

    capabilities = build_browser_plan()["forms"][0]["capabilities"]

    [policy] = capabilities["staticContent"]["declarations"]
    assert policy["sectionName"] == "directions"
    assert policy["paragraphs"]
    assert len(policy["sha256"]) == 64
    assert {
        declaration["responsePath"] for declaration in capabilities["readOnly"]["declarations"]
    } == {"/authorized_representative_signature", "/submitted_date"}
    assert capabilities["conditional"]["applicability"] == "not_applicable"


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
    assert [
        (source["type"], source["uri"], source["sha256"]) for source in evidence["sources"]
    ] == [
        (
            "xsd",
            "https://apply07.grants.gov/apply/forms/schemas/GG_LobbyingForm-V1.1.xsd",
            "a41d88b19e240dbb5f9b13815c0426d2396414fc1af8d6ab6a96f35855a0a5f7",
        ),
        (
            "pdf",
            "https://apply07.grants.gov/apply/forms/readonly/GG_LobbyingForm-V1.1.pdf",
            "9c8194fd874951382f448a047c81fe1a901f5f70cb9bfeb7e31a7478748b6439",
        ),
        (
            "dat",
            "https://apply07.grants.gov/apply/forms/sample/GG_LobbyingForm-V1.1_F255.xls",
            "4489cf1e023991a36a49d4015b323fb87ad152dfa915ef750f0f19c5d5138ba2",
        ),
        (
            "instructions",
            "https://apply07.grants.gov/apply/forms/instructions/GG_LobbyingForm-V1.1-Instructions.pdf",
            "72062133a94e4757b90a8694c900d5303daa62d2093f3d4444f1aae0bb5ba0e8",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/Global-V1.0.xsd",
            "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/GlobalLibrary-V2.0.xsd",
            "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/UniversalCodes-V2.0.xsd",
            "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
        ),
        (
            "implementation",
            "https://github.com/mikec-ai/simpler-grants-gov/blob/30dd50cf0493146c32f89f78398979523e040080/api/src/form_schema/forms/gg_lobbying_form/1/0/form_json.py",
            "bdf73a05a75b5020218f06864118f4c1e9ccc396934feaccc49e9acbbe406ad8",
        ),
    ]
    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "artifact": "artifacts/proof/grantsgov-GGLobbyingForm.jsonl.manifest.json",
        "sourceSetSha256": "b545bd44a103bba32721c07e7e1dd0d708e5435b416a2ccf1005cc4de9325895",
        "extractedAt": "2026-08-18T19:43:18.826487Z",
    }


def test_gg_lobbying_canary_is_not_registered_before_release_review() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())

    assert "gg-lobbying" not in registrations["forms"]

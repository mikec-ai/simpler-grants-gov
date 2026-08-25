"""Portable CD-511 conformance canary against the existing SGG oracle."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.browser_plan import build_browser_plan
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)

VALID_RESPONSE = {
    "applicant_name": "Example Research Institute",
    "project_name": "Portable Grants Forms",
    "contact_person": {"first_name": "Ada", "last_name": "Lovelace"},
    "contact_person_title": "Authorized Representative",
}
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
XSD_NAME = "CD511-V1.1.xsd"
XSD_SHA256 = "f13c05b8e62fe1e7cf0198053f79fdd34efe4b7d10b56974d27a7dd45d013fde"


def test_cd511_loads_without_a_form_specific_projection_profile() -> None:
    projected = load_form("cd511")

    assert projected.meta == {
        "id": "cd511",
        "legacyFormId": 276,
        "formName": "CD511",
        "shortFormName": "CD511",
        "formVersion": "1.1",
        "agencyCode": "SGG",
        "ombNumber": "",
    }
    assert len(projected.form_ui_schema) == 7
    assert [section["name"] for section in projected.form_ui_schema[:4]] == [
        "directions1",
        "directions2",
        "directions3",
        "directions4",
    ]


def test_cd511_executes_the_portable_award_or_project_constraint() -> None:
    assert_validation_case(
        "cd511",
        ValidationCase("project name", VALID_RESPONSE, frozenset()),
    )
    award = copy.deepcopy(VALID_RESPONSE)
    award.pop("project_name")
    award["award_number"] = "AWARD-123"
    assert_validation_case(
        "cd511",
        ValidationCase("award number", award, frozenset()),
    )
    missing = copy.deepcopy(VALID_RESPONSE)
    missing.pop("project_name")
    assert_validation_case(
        "cd511",
        ValidationCase("neither identifier", missing, frozenset({"$"})),
    )


def test_cd511_preserves_source_limits_and_aor_name_requiredness() -> None:
    schema = resolve_jsonschema(copy.deepcopy(load_form("cd511").form_json_schema))

    assert schema["properties"]["award_number"]["maxLength"] == 25
    assert schema["properties"]["project_name"]["maxLength"] == 60
    assert schema["properties"]["contact_person"]["required"] == [
        "first_name",
        "last_name",
    ]


def test_cd511_submit_populates_signature_and_date_through_generic_rules() -> None:
    application_form = submit_form("cd511", VALID_RESPONSE)
    response = application_form.application_response

    assert response["signature"] == "reviewer@example.gov"
    assert len(response["submitted_date"].split("-")) == 3
    assert_json_round_trip(response)


def test_cd511_submitter_output_emits_exact_xsd_valid_xml() -> None:
    application_form = submit_form("cd511", VALID_RESPONSE)
    projected = load_form("cd511")
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=application_form.application_response,
            transform_config=projected.json_to_xml_schema,
        )
    )

    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    assert "<CD511:Signature>reviewer@example.gov</" in generated.xml_data
    xsd = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == XSD_SHA256
    validation = XSDValidator(XSD_DIRECTORY).validate_xml(generated.xml_data, xsd)
    assert validation["valid"], validation


def test_cd511_browser_plan_preserves_policy_without_accepting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ENABLE_PORTABLE_FORM_PREVIEW", "true")
    monkeypatch.setenv("PORTABLE_BROWSER_FORM_IDS", "cd511")

    capabilities = build_browser_plan()["forms"][0]["capabilities"]

    assert len(capabilities["staticContent"]["declarations"]) == 4
    assert all(
        declaration["paragraphs"] and len(declaration["sha256"]) == 64
        for declaration in capabilities["staticContent"]["declarations"]
    )
    assert {
        declaration["responsePath"] for declaration in capabilities["readOnly"]["declarations"]
    } == {"/signature", "/submitted_date"}
    assert capabilities["conditional"]["applicability"] == "not_applicable"


def test_cd511_keeps_policy_and_evidence_pins_with_the_runtime_selection() -> None:
    root = ARTIFACTS / "forms/cd511"
    policy = json.loads((root / "policy-content.json").read_text())
    binding = json.loads((root / "policy-binding.json").read_text())
    evidence = json.loads((root / "evidence.json").read_text())

    assert policy["sources"][0]["sha256"] == (
        "9c77e249ecb0755f6e000eaa0becd9f6a459fe91adf766f2c64e898d6253d92e"
    )
    assert binding["release"]["status"] == "draft"
    assert evidence["semanticReview"]["status"] == "proposed"
    assert [
        (source["type"], source["uri"], source["sha256"]) for source in evidence["sources"]
    ] == [
        (
            "xsd",
            "https://apply07.grants.gov/apply/forms/schemas/CD511-V1.1.xsd",
            "f13c05b8e62fe1e7cf0198053f79fdd34efe4b7d10b56974d27a7dd45d013fde",
        ),
        (
            "dat",
            "https://apply07.grants.gov/apply/forms/sample/CD511-V1.1_F276.xls",
            "0910535d9bf55262ae383482e8e18753b142b828fb580b68cf452a5fc6e2ed8e",
        ),
        (
            "pdf",
            "https://apply07.grants.gov/apply/forms/readonly/CD511-V1.1.pdf",
            "9c77e249ecb0755f6e000eaa0becd9f6a459fe91adf766f2c64e898d6253d92e",
        ),
        (
            "implementation",
            "https://github.com/mikec-ai/simpler-grants-gov/blob/30dd50cf0493146c32f89f78398979523e040080/api/src/form_schema/forms/cd511/1/0/form_json.py",
            "573a8757193f0fdb7c79ed8099b66ef936f067254cbf442679768750a6a6ae2e",
        ),
    ]


def test_cd511_canary_is_not_registered_before_release_review() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())

    assert "cd511" not in registrations["forms"]

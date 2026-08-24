"""The existing SF-424 declaration must survive the generic Simpler adapter unchanged."""

import copy
import json
from pathlib import Path

import pytest

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.loader import build_runtime_form, load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec import parity

FORM_DIR = "sf424"

RENDERED = {
    "/properties/date_received#readOnly": "canonical declaration preserves computed behavior",
    "/properties/project_start_date#description": "removes trailing whitespace",
    "/properties/project_end_date#description": "removes trailing whitespace",
    "/properties/debt_explanation#description": "attachment question supplies help text",
    "/properties/authorized_representative_email#maxLength": "shared email constraint is explicit",
    "/properties/total_estimated_funding#readOnly": "canonical declaration preserves computed behavior",
    "/properties/aor_signature#readOnly": "canonical declaration preserves system-managed behavior",
    "/properties/date_signed#readOnly": "canonical declaration preserves system-managed behavior",
}
ALLOWED_BEHAVIOR = {
    ("authorized_representative_email", "maxLength"): "shared email constraint is explicit",
}


@pytest.fixture(scope="module")
def golden():
    return load_versioned_form(Path(forms_package.__file__).parent / FORM_DIR, "1.0")


@pytest.fixture(scope="module")
def projected():
    return load_form("sf424")


@pytest.fixture(scope="module")
def resolved_golden(golden):
    return resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))


@pytest.fixture(scope="module")
def resolved_projected(projected):
    return resolve_jsonschema(copy.deepcopy(projected.form_json_schema))


@pytest.fixture
def seeds():
    minimal = {
        "submission_type": "Application",
        "application_type": "New",
        "organization_name": "Example Org",
        "employer_taxpayer_identification_number": "123-456-7890",
        "sam_uei": "UEI123123123",
        "applicant": {
            "street1": "123 Main St",
            "city": "Exampleburg",
            "state": "NY: New York",
            "country": "USA: UNITED STATES",
            "zip_code": "12345",
        },
        "contact_person": {"first_name": "Bob", "last_name": "Smith"},
        "phone_number": "123-456-7890",
        "email": "example@mail.com",
        "applicant_type_code": ["P: Individual"],
        "agency_name": "Department of Research",
        "funding_opportunity_number": "ABC-123",
        "funding_opportunity_title": "My Example Opportunity",
        "project_title": "My Project",
        "congressional_district_applicant": "MI.345",
        "congressional_district_program_project": "MI.567",
        "project_start_date": "2026-01-01",
        "project_end_date": "2026-12-31",
        "federal_estimated_funding": "5000.00",
        "applicant_estimated_funding": "1000.00",
        "state_estimated_funding": "2000.00",
        "local_estimated_funding": "1000.00",
        "other_estimated_funding": "0.00",
        "program_income_estimated_funding": "10.00",
        "total_estimated_funding": "9010.00",
        "state_review": "c. Program is not covered by E.O. 12372.",
        "delinquent_federal_debt": False,
        "certification_agree": True,
        "authorized_representative": {"first_name": "Bob", "last_name": "Smith"},
        "authorized_representative_title": "Doctor",
        "authorized_representative_phone_number": "123-456-7890",
        "authorized_representative_email": "example@mail.com",
    }
    full = minimal | {
        "application_type": "Revision",
        "revision_type": "E: Other (specify)",
        "revision_other_specify": "Other revision",
        "federal_award_identifier": "1234567890",
        "department_name": "Department of Research",
        "division_name": "Science",
        "contact_person_title": "Director",
        "organization_affiliation": "Research Division",
        "fax": "123-456-7890",
        "applicant_type_code": ["P: Individual", "X: Other (specify)"],
        "applicant_type_other_specify": "Other applicant",
        "assistance_listing_number": "12.345",
        "assistance_listing_program_title": "Research",
        "competition_identification_number": "ABC-XYZ-123",
        "competition_identification_title": "Research Project",
        "areas_affected": "06dea634-6882-4ffc-805c-f1e3e43038c7",
        "additional_project_title": ["e7293742-d325-4f11-88ac-c17e58a775e4"],
        "additional_congressional_districts": "9003399d-93ea-42db-a80b-c3f94fc1aa16",
        "state_review": "a. This application was made available to the state under the Executive Order 12372 Process for review on",
        "state_review_available_date": "2025-05-31",
        "delinquent_federal_debt": True,
        "debt_explanation": "fc1c203a-4890-4237-a54f-8a66a7938cca",
        "authorized_representative_fax": "333-333-3333",
        "aor_signature": "Bob Smith",
        "date_signed": "2025-06-01",
    }
    return [minimal, full]


def test_ui_and_rule_schemas_are_identical(projected, golden):
    assert projected.form_ui_schema == golden.FORM_UI_SCHEMA
    assert projected.form_rule_schema == golden.FORM_RULE_SCHEMA


def test_runtime_adapter_expands_portable_references_for_simpler():
    runtime = build_runtime_form("sf424")

    assert '"$ref"' not in json.dumps(runtime.form_json_schema)
    assert runtime.form_json_schema["properties"]["submission_type"]["allOf"][0]["type"] == "string"


def test_every_rendered_difference_is_bounded(resolved_projected, resolved_golden, golden):
    differences = parity.rendered_differences(
        resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA
    )
    assert parity.unexplained(differences, RENDERED) == []
    assert parity.unused(differences, RENDERED) == []


def test_conditional_requiredness_is_identical(resolved_projected, resolved_golden):
    assert parity.conditional_branches(resolved_projected) == parity.conditional_branches(
        resolved_golden
    )


def test_validation_verdicts_are_identical_except_bounded_constraint(
    resolved_projected, resolved_golden, seeds
):
    payloads = parity.corpus(resolved_golden, seeds)
    assert len(payloads) > 450
    assert (
        parity.behavioral_differences(
            resolved_projected, resolved_golden, payloads, ALLOWED_BEHAVIOR
        )
        == []
    )

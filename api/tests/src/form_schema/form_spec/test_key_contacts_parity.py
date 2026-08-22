"""Key Contacts, authored declaratively, must behave exactly like the hand-written form.

The hand-written `form_json.py` is the oracle. Nothing about it is modified; the projected
artifacts have to meet it.
"""

import copy

import pytest

from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec import parity

FORM_DIR = "key_contacts"

#: Differences between what this form renders and what the golden renders. Each key is
#: `<pointer>#<keyword>`, each value says why the difference is deliberate, and anything not
#: listed fails the test.
RENDERED = {
    # SGG's shared `phone_number` and `contact_email` carry no description at all, so these
    # three fields render with no help text today. The bank's questions describe themselves,
    # which is additive: an applicant gains a line of guidance.
    "/properties/key_contacts/items/properties/phone#description": "bank question describes itself",
    "/properties/key_contacts/items/properties/fax#description": "bank question describes itself",
    "/properties/key_contacts/items/properties/email#description": "bank question describes itself",
}

#: Verdicts that differ. Empty, and worth keeping that way.
ALLOWED_BEHAVIOR: dict[tuple[str, str], str] = {}


@pytest.fixture(scope="module")
def golden():
    from pathlib import Path

    import src.form_schema.forms as forms_package

    root = Path(forms_package.__file__).parent / FORM_DIR
    return load_versioned_form(root, "1.0")


@pytest.fixture(scope="module")
def projected():
    return load_form("key-contacts")


@pytest.fixture(scope="module")
def resolved_golden(golden):
    return resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))


@pytest.fixture(scope="module")
def resolved_projected(projected):
    return resolve_jsonschema(copy.deepcopy(projected.form_json_schema))


@pytest.fixture
def seeds():
    """The golden's own fixtures: one fully populated contact and one minimal one."""
    full = {
        "project_role": "Principal Investigator",
        "name": {
            "prefix": "Doctor",
            "first_name": "Sue",
            "middle_name": "Sally",
            "last_name": "Storm",
            "suffix": "Esquire",
        },
        "title": "Director",
        "organizational_affiliation": "Acme University",
        "address": {
            "street1": "123 Main Street",
            "street2": "Apt 123",
            "city": "Placeville",
            "county": "Placeville County",
            "state": "WY: Wyoming",
            "province": "Nowhere",
            "zip_code": "56789-1234",
            "country": "USA: UNITED STATES",
        },
        "phone": "1234567890",
        "fax": "1112223333",
        "email": "example@example.com",
    }
    minimal = {
        "project_role": "Project Manager",
        "name": {"first_name": "Joe", "last_name": "Smithers"},
        "address": {"street1": "456 Rio", "city": "Montevideo", "country": "URY: URUGUAY"},
        "phone": "1234567890",
        "email": "person@place.com",
    }
    return [
        {"applicant_organization_name": "Acme Corporation", "key_contacts": [full, minimal]},
        {"applicant_organization_name": "Acme Corporation", "key_contacts": [minimal]},
    ]


def test_ui_schema_is_identical(projected, golden):
    """Same UI, plus the portable list's explicit schema pointer."""
    expected = copy.deepcopy(golden.FORM_UI_SCHEMA)
    expected[0]["children"][1]["definition"] = "/properties/key_contacts"
    assert projected.form_ui_schema == expected


def test_rule_schema_is_identical(projected, golden):
    assert projected.form_rule_schema == getattr(golden, "FORM_RULE_SCHEMA", None)


def test_every_rendered_field_matches(resolved_projected, resolved_golden, golden):
    """What an applicant reads, field by field, keyed by what the form renders."""
    differences = parity.rendered_differences(
        resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA
    )
    assert parity.unexplained(differences, RENDERED) == []


def test_allow_list_has_no_dead_entries(resolved_projected, resolved_golden, golden):
    """An explanation for a difference that no longer exists is an explanation to delete."""
    differences = parity.rendered_differences(
        resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA
    )
    assert parity.unused(differences, RENDERED) == []


def test_conditional_requiredness_matches(resolved_projected, resolved_golden):
    assert parity.conditional_branches(resolved_projected) == parity.conditional_branches(
        resolved_golden
    )


def test_no_reference_is_left_unresolved(resolved_projected):
    """A reference that failed to resolve would leave a `$ref` behind."""

    def refs(node):
        if isinstance(node, dict):
            return "$ref" in node or any(refs(v) for v in node.values())
        if isinstance(node, list):
            return any(refs(v) for v in node)
        return False

    assert not refs(resolved_projected)


def test_validation_verdicts_are_identical(resolved_projected, resolved_golden, seeds):
    """What an applicant may submit, over a corpus derived from the golden."""
    payloads = parity.corpus(resolved_golden, seeds)
    assert len(payloads) > 100, "the corpus should exercise every field"
    assert (
        parity.behavioral_differences(
            resolved_projected, resolved_golden, payloads, ALLOWED_BEHAVIOR
        )
        == []
    )

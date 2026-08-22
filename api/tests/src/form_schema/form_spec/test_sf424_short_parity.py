"""The existing SF-424 Short declaration must survive the generic Simpler adapter."""

import copy
from pathlib import Path
from typing import Any, cast

import pytest

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec import parity
from tests.src.form_schema.forms import test_sf424_short as golden_fixtures

FORM_DIR = "sf424_short"

RENDERED: dict[str, str] = {
    "/properties/agency_name#readOnly": "canonical declaration preserves opportunity-supplied behavior",
    "/properties/assistance_listing_number#readOnly": "canonical declaration preserves opportunity-supplied behavior",
    "/properties/assistance_listing_program_title#readOnly": "canonical declaration preserves opportunity-supplied behavior",
    "/properties/funding_opportunity_number#readOnly": "canonical declaration preserves opportunity-supplied behavior",
    "/properties/funding_opportunity_title#readOnly": "canonical declaration preserves opportunity-supplied behavior",
    "/properties/sam_uei#readOnly": "canonical declaration preserves organization-supplied behavior",
}


@pytest.fixture(scope="module")
def golden() -> Any:
    return load_versioned_form(Path(forms_package.__file__).parent / FORM_DIR, "1.0")


@pytest.fixture(scope="module")
def projected() -> Any:
    return load_form("sf424-short")


@pytest.fixture(scope="module")
def resolved_golden(golden: Any) -> dict[str, Any]:
    return resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))


@pytest.fixture(scope="module")
def resolved_projected(projected: Any) -> dict[str, Any]:
    return resolve_jsonschema(copy.deepcopy(projected.form_json_schema))


@pytest.fixture
def seeds() -> list[dict[str, Any]]:
    """Reuse the hand-written form's minimal and full payload oracles."""
    contact = cast(Any, golden_fixtures.contact_person_group).__wrapped__()
    minimal = cast(Any, golden_fixtures.valid_json_v3_0).__wrapped__(contact)
    full = cast(Any, golden_fixtures.full_valid_json_v3_0).__wrapped__(minimal, contact)
    return [minimal, full]


def test_ui_and_rule_schemas_are_identical(projected: Any, golden: Any) -> None:
    assert projected.form_ui_schema == golden.FORM_UI_SCHEMA
    assert projected.form_rule_schema == golden.FORM_RULE_SCHEMA


def test_every_rendered_difference_is_bounded(
    resolved_projected: dict[str, Any], resolved_golden: dict[str, Any], golden: Any
) -> None:
    differences = parity.rendered_differences(
        resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA
    )
    assert parity.unexplained(differences, RENDERED) == []
    assert parity.unused(differences, RENDERED) == []


def test_conditional_requiredness_is_identical(
    resolved_projected: dict[str, Any], resolved_golden: dict[str, Any]
) -> None:
    assert parity.conditional_branches(resolved_projected) == parity.conditional_branches(
        resolved_golden
    )


def test_validation_verdicts_are_identical(
    resolved_projected: dict[str, Any],
    resolved_golden: dict[str, Any],
    seeds: list[dict[str, Any]],
) -> None:
    payloads = parity.corpus(resolved_golden, seeds)
    assert len(payloads) > 500
    assert parity.behavioral_differences(resolved_projected, resolved_golden, payloads) == []

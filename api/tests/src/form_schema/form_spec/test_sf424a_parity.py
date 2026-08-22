"""The existing SF-424A declaration must survive the generic Simpler adapter."""

import copy
from pathlib import Path
from typing import Any, cast

import pytest

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec import parity
from tests.src.form_schema.forms import test_sf424a as golden_fixtures

FORM_DIR = "sf424a"

RENDERED = {
    "/properties/total_budget_summary#title": "shared budget block supplies a heading",
    "/properties/total_budget_summary#description": "shared budget block supplies guidance",
    "/properties/total_budget_categories#title": "shared budget block supplies a heading",
    "/properties/total_budget_categories#description": "shared budget block supplies guidance",
    "/properties/total_non_federal_resources#title": "shared budget block supplies a heading",
    "/properties/total_non_federal_resources#description": "shared budget block supplies guidance",
    "/properties/total_federal_fund_estimates#title": "shared budget block supplies a heading",
    "/properties/total_federal_fund_estimates#description": "shared budget block supplies guidance",
}


@pytest.fixture(scope="module")
def golden() -> Any:
    return load_versioned_form(Path(forms_package.__file__).parent / FORM_DIR, "1.0")


@pytest.fixture(scope="module")
def projected() -> Any:
    return load_form("sf424a")


@pytest.fixture(scope="module")
def resolved_golden(golden: Any) -> dict[str, Any]:
    return resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))


@pytest.fixture(scope="module")
def resolved_projected(projected: Any) -> dict[str, Any]:
    return resolve_jsonschema(copy.deepcopy(projected.form_json_schema))


@pytest.fixture
def seeds() -> list[dict[str, Any]]:
    """Reuse the hand-written form's minimal and full payload oracles."""
    minimal_item = cast(Any, golden_fixtures.minimal_valid_activity_line_item_v1_0).__wrapped__()
    full_item = cast(Any, golden_fixtures.full_valid_activity_line_item_v1_0).__wrapped__()
    return [
        cast(Any, golden_fixtures.minimal_valid_json_v1_0).__wrapped__(minimal_item),
        cast(Any, golden_fixtures.full_valid_json_v1_0).__wrapped__(full_item),
    ]


def _calculation_count(node: Any) -> int:
    if isinstance(node, dict):
        return int("gg_pre_population" in node) + sum(
            _calculation_count(value) for value in node.values()
        )
    if isinstance(node, list):
        return sum(_calculation_count(value) for value in node)
    return 0


def test_ui_and_rule_schemas_are_identical(projected: Any, golden: Any) -> None:
    assert projected.form_ui_schema == golden.FORM_UI_SCHEMA
    assert projected.form_rule_schema == golden.FORM_RULE_SCHEMA
    assert _calculation_count(projected.form_rule_schema) == 35


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
    assert len(payloads) > 350
    assert parity.behavioral_differences(resolved_projected, resolved_golden, payloads) == []

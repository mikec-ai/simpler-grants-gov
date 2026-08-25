"""Consumer conformance for source-exact R&R Budget guidance and date ordering."""

import json
import re
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.form_schema.form_spec.loader import LoadedForm, load_form
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context

DIRECT_PROFILES = ("rr-budget", "rr-budget-10yr")
NESTED_PROFILES = (
    "rr-subaward-budget",
    "rr-subaward-budget-30",
    "rr-subaward-budget-10yr-30",
)
ALL_PROFILES = (*DIRECT_PROFILES, *NESTED_PROFILES)

EXPECTED_DESCRIPTIONS = {
    ("equipment", "additional_equipments_attachment"): (
        "One possible attachment per budget period. Required if "
        "TotalFundForAttachedEquipment is entered and greater than zero."
    ),
    ("equipment", "total_fund_for_attached_equipment"): (
        "Required and must be greater than zero if an AdditionalEquipmentsAttachment exists."
    ),
    ("key_persons", "attached_key_persons"): (
        "One possible attachment per budget period. Required if "
        "TotalFundForAttachedKeyPersons is entered and greater than zero."
    ),
    ("key_persons", "total_fund_for_attached_key_persons"): (
        "Required and must be greater than zero if an AttachedKeyPersons attachment exists."
    ),
}


def _budget_period_properties(form: LoadedForm, *, nested: bool) -> dict[str, Any]:
    properties = form.form_json_schema["properties"]
    if nested:
        properties = properties["budget_attachments"]["items"]["properties"]
    return properties["budget_year"]["items"]["properties"]


def _validation_context(form: LoadedForm, application_response: dict[str, Any]) -> JsonRuleContext:
    application_form = SimpleNamespace(
        application_response=application_response,
        application=SimpleNamespace(application_attachments=[]),
        form=form,
        application_form_id=f"portable-{form.form_id}-date-order-test",
        form_id=form.form_id,
    )
    return JsonRuleContext(
        cast(Any, application_form),
        JsonRuleConfig(
            do_pre_population=False,
            do_post_population=False,
            do_field_validation=True,
        ),
    )


@pytest.mark.parametrize("form_id", ALL_PROFILES)
def test_source_exact_budget_guidance_is_visible_in_every_profile(form_id: str) -> None:
    form = load_form(form_id)
    properties = _budget_period_properties(form, nested=form_id in NESTED_PROFILES)

    assert properties["budget_period_end_date"]["description"] == (
        "End Date cannot be before Start Date."
    )
    for (group, field), expected in EXPECTED_DESCRIPTIONS.items():
        assert properties[group]["properties"][field]["description"] == expected


@pytest.mark.parametrize("form_id", DIRECT_PROFILES)
def test_direct_budget_date_ordering_is_scoped_to_each_period(form_id: str) -> None:
    form = load_form(form_id)
    context = _validation_context(
        form,
        {
            "budget_year": [
                {
                    "budget_period_start_date": "2027-01-01",
                    "budget_period_end_date": "2027-12-31",
                },
                {
                    "budget_period_start_date": "2028-12-31",
                    "budget_period_end_date": "2028-01-01",
                },
            ]
        },
    )

    process_rule_schema_for_context(context)

    assert [issue.field for issue in context.validation_issues] == [
        "$.budget_year[1].budget_period_end_date"
    ]


@pytest.mark.parametrize("form_id", NESTED_PROFILES)
def test_nested_budget_date_ordering_is_scoped_to_each_subaward_and_period(
    form_id: str,
) -> None:
    form = load_form(form_id)
    context = _validation_context(
        form,
        {
            "budget_attachments": [
                {
                    "budget_year": [
                        {
                            "budget_period_start_date": "2027-01-01",
                            "budget_period_end_date": "2027-12-31",
                        },
                        {
                            "budget_period_start_date": "2028-12-31",
                            "budget_period_end_date": "2028-01-01",
                        },
                    ]
                },
                {
                    "budget_year": [
                        {
                            "budget_period_start_date": "2029-06-30",
                            "budget_period_end_date": "2029-01-01",
                        }
                    ]
                },
            ]
        },
    )

    process_rule_schema_for_context(context)

    assert [issue.field for issue in context.validation_issues] == [
        "$.budget_attachments[0].budget_year[1].budget_period_end_date",
        "$.budget_attachments[1].budget_year[0].budget_period_end_date",
    ]


def test_promotion_preserves_integrity_and_immutable_source_revision() -> None:
    # Import here so the test exercises the same fail-closed bank boundary as runtime loading.
    from src.form_schema.form_spec.bank import ARTIFACT_MANIFEST, verify_artifacts

    manifest = verify_artifacts()
    assert manifest == json.loads(ARTIFACT_MANIFEST.read_text())
    assert manifest["source"]["repository"] == ("https://github.com/mikec-ai/grants-form-spec.git")
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["source"]["revision"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["sourceBundleSha256"])
    assert len(manifest["selection"]["forms"]) == 42

"""DB-backed lifecycle evidence for the portable SF-424A implementation."""

import copy

from sqlalchemy import select

from src.constants.lookup_constants import ApplicationFormStatus
from src.db.models.competition_models import ApplicationForm
from src.form_schema.forms import SF424a_v1_0
from src.services.applications.application_validation import (
    ApplicationAction,
    validate_application_form,
)
from tests.src.db.models.factories import (
    ApplicationFactory,
    ApplicationFormFactory,
    CompetitionFormFactory,
)
from tests.src.form_schema.form_spec.lifecycle import (
    register_runtime_form_for_test,
    restore_runtime_form_after_test,
)
from tests.src.form_schema.forms import test_sf424a as golden_fixtures


def _valid_response_with_manual_column_g() -> dict:
    line_item = copy.deepcopy(golden_fixtures.full_valid_activity_line_item_v1_0.__wrapped__())
    line_item["budget_summary"].update(
        {
            "federal_estimated_unobligated_amount": "1.00",
            "non_federal_estimated_unobligated_amount": "2.00",
            "federal_new_or_revised_amount": "3.00",
            "non_federal_new_or_revised_amount": "4.00",
            "total_amount": "100.00",
        }
    )
    response = golden_fixtures.full_valid_json_v1_0.__wrapped__(line_item)
    response.update(
        {
            "direct_charges_explanation": "Direct charges explanation",
            "indirect_charges_explanation": "Indirect charges explanation",
            "remarks": "Lifecycle fixture remarks",
        }
    )
    return response


def test_sf424a_manual_column_g_survives_database_reload_and_validation(
    db_session, enable_factory_create, load_active_forms
) -> None:
    response = _valid_response_with_manual_column_g()
    application = ApplicationFactory.create(competition__competition_forms=[])
    competition_form = CompetitionFormFactory.create(
        competition=application.competition,
        form=SF424a_v1_0,
    )
    application_form = ApplicationFormFactory.create(
        application=application,
        competition_form=competition_form,
        application_response=response,
    )

    errors = validate_application_form(application_form, ApplicationAction.MODIFY)
    assert errors == []
    assert application_form.application_form_status is ApplicationFormStatus.COMPLETE
    assert (
        application_form.application_response["activity_line_items"][0]["budget_summary"][
            "total_amount"
        ]
        == "100.00"
    )
    assert application_form.application_response["total_budget_summary"]["total_amount"] == "100.00"

    # Persist the post-rule response through the same JSON column used by the API,
    # then force a new database read before exercising GET-time validation.
    application_form.application_response = copy.deepcopy(application_form.application_response)
    application_form_id = application_form.application_form_id
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.execute(
        select(ApplicationForm).where(ApplicationForm.application_form_id == application_form_id)
    ).scalar_one()
    assert (
        reloaded.application_response["activity_line_items"][0]["budget_summary"]["total_amount"]
        == "100.00"
    )
    assert reloaded.application_response["total_budget_summary"]["total_amount"] == "100.00"
    assert validate_application_form(reloaded, ApplicationAction.GET) == []
    assert (
        reloaded.application_response["activity_line_items"][0]["budget_summary"]["total_amount"]
        == "100.00"
    )
    assert reloaded.application_response["total_budget_summary"]["total_amount"] == "100.00"


def test_sf424a_legacy_blanks_validate_without_rewriting_capture_through_submit(
    db_session, enable_factory_create, load_active_forms
) -> None:
    portable, key, previous = register_runtime_form_for_test("sf424a")
    try:
        response = _valid_response_with_manual_column_g()
        for field in (
            "direct_charges_explanation",
            "indirect_charges_explanation",
            "remarks",
        ):
            response[field] = ""
        application = ApplicationFactory.create(competition__competition_forms=[])
        competition_form = CompetitionFormFactory.create(
            competition=application.competition,
            form=portable,
        )
        application_form = ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response=response,
        )

        assert validate_application_form(application_form, ApplicationAction.MODIFY) == []
        assert application_form.application_form_status is ApplicationFormStatus.COMPLETE
        for field in (
            "direct_charges_explanation",
            "indirect_charges_explanation",
            "remarks",
        ):
            assert application_form.application_response[field] == ""

        application_form_id = application_form.application_form_id
        application_form.application_response = copy.deepcopy(application_form.application_response)
        db_session.flush()
        db_session.expire_all()
        reloaded = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == application_form_id
            )
        ).scalar_one()

        assert validate_application_form(reloaded, ApplicationAction.GET) == []
        assert validate_application_form(reloaded, ApplicationAction.SUBMIT) == []
        for field in (
            "direct_charges_explanation",
            "indirect_charges_explanation",
            "remarks",
        ):
            assert reloaded.application_response[field] == ""
        assert reloaded.application_response["total_budget_summary"]["total_amount"] == "100.00"
    finally:
        restore_runtime_form_after_test(key, previous)

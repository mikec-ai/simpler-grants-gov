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
from tests.src.form_schema.forms import test_sf424a as golden_fixtures


def _valid_response_with_manual_column_g() -> dict:
    line_item = copy.deepcopy(golden_fixtures.full_valid_activity_line_item_v1_0.__wrapped__())
    line_item["budget_summary"].update({
        "federal_estimated_unobligated_amount": "1.00",
        "non_federal_estimated_unobligated_amount": "2.00",
        "federal_new_or_revised_amount": "3.00",
        "non_federal_new_or_revised_amount": "4.00",
        "total_amount": "100.00",
    })
    return golden_fixtures.full_valid_json_v1_0.__wrapped__(line_item)


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

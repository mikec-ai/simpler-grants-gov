"""End-to-end service proof for portable initial cross-form population."""

from typing import Any

import pytest
from sqlalchemy import select

from src.constants.lookup_constants import Privilege
from src.db.models.competition_models import ApplicationForm
from src.services.applications.update_application_form import update_application_form
from tests.src.db.models.factories import (
    ApplicationFactory,
    ApplicationFormFactory,
    ApplicationUserFactory,
    ApplicationUserRoleFactory,
    CompetitionFactory,
    CompetitionFormFactory,
    OrganizationFactory,
    RoleFactory,
    UserFactory,
)
from tests.src.form_schema.form_spec.lifecycle import (
    register_runtime_form_for_test,
    restore_runtime_form_after_test,
)


def _user_with_modify_access(application: Any) -> Any:
    user = UserFactory.create()
    ApplicationUserRoleFactory.create(
        application_user=ApplicationUserFactory.create(user=user, application=application),
        role=RoleFactory.create(
            privileges=[Privilege.MODIFY_APPLICATION], is_application_role=True
        ),
    )
    return user


def _source_response(
    *,
    sam_uei: str = "ABCDEFGHIJKL",
    organization_name: str = "Example Research University",
    proposed_start_date: str = "2027-07-01",
) -> dict[str, Any]:
    return {
        "applicant_info": {
            "organization_info": {
                "sam_uei": sam_uei,
                "organization_name": organization_name,
            }
        },
        "proposed_project_period": {"proposed_start_date": proposed_start_date},
    }


@pytest.mark.parametrize("budget_form_id", ["rr-budget", "rr-budget-10yr"])
def test_source_save_populates_budget_and_never_overwrites_applicant_edits(
    enable_factory_create: Any,
    db_session: Any,
    budget_form_id: str,
) -> None:
    source_form, source_key, previous_source = register_runtime_form_for_test("rr-sf424")
    budget_form, budget_key, previous_budget = register_runtime_form_for_test(budget_form_id)
    sam_uei = "ABCDEFGHIJKL" if budget_form_id == "rr-budget" else "ABCDEFGHIJ10"
    try:
        competition = CompetitionFactory.create(competition_forms=[])
        source_competition_form = CompetitionFormFactory.create(
            competition=competition, form=source_form
        )
        budget_competition_form = CompetitionFormFactory.create(
            competition=competition, form=budget_form
        )
        application = ApplicationFactory.create(
            competition=competition,
            organization=OrganizationFactory.create(sam_gov_entity__uei=sam_uei),
        )
        ApplicationFormFactory.create(
            application=application,
            competition_form=source_competition_form,
            application_response={},
        )
        budget_application_form = ApplicationFormFactory.create(
            application=application,
            competition_form=budget_competition_form,
            application_response={},
        )
        user = _user_with_modify_access(application)

        update_application_form(
            db_session,
            application.application_id,
            source_form.form_id,
            user,
            application_response=_source_response(sam_uei=sam_uei),
        )
        db_session.commit()

        db_session.expire_all()
        populated = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == budget_application_form.application_form_id
            )
        ).scalar_one()
        assert populated.application_response == {
            "samuei": sam_uei,
            "organization_name": "Example Research University",
            "budget_year": [{"budget_period_start_date": "2027-07-01"}],
        }

        applicant_response = {
            **populated.application_response,
            "organization_name": "Applicant-confirmed Organization",
        }
        update_application_form(
            db_session,
            application.application_id,
            budget_form.form_id,
            user,
            application_response=applicant_response,
        )
        db_session.commit()
        db_session.expire_all()
        applicant_saved_response = db_session.execute(
            select(ApplicationForm.application_response).where(
                ApplicationForm.application_form_id == budget_application_form.application_form_id
            )
        ).scalar_one()
        assert applicant_saved_response["organization_name"] == ("Applicant-confirmed Organization")
        update_application_form(
            db_session,
            application.application_id,
            source_form.form_id,
            user,
            application_response=_source_response(
                sam_uei="ZZZZZZZZZZZZ",
                organization_name="Changed Source Organization",
                proposed_start_date="2028-01-01",
            ),
        )
        db_session.commit()

        db_session.expire_all()
        preserved = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == budget_application_form.application_form_id
            )
        ).scalar_one()
        assert preserved.application_response == applicant_saved_response
    finally:
        restore_runtime_form_after_test(source_key, previous_source)
        restore_runtime_form_after_test(budget_key, previous_budget)


@pytest.mark.parametrize("budget_form_id", ["rr-budget", "rr-budget-10yr"])
def test_missing_source_values_are_skipped_without_constructing_empty_targets(
    enable_factory_create: Any,
    db_session: Any,
    budget_form_id: str,
) -> None:
    source_form, source_key, previous_source = register_runtime_form_for_test("rr-sf424")
    budget_form, budget_key, previous_budget = register_runtime_form_for_test(budget_form_id)
    sam_uei = "MNOPQRSTUVWX" if budget_form_id == "rr-budget" else "MNOPQRSTUV10"
    try:
        competition = CompetitionFactory.create(competition_forms=[])
        source_competition_form = CompetitionFormFactory.create(
            competition=competition, form=source_form
        )
        budget_competition_form = CompetitionFormFactory.create(
            competition=competition, form=budget_form
        )
        application = ApplicationFactory.create(
            competition=competition,
            organization=OrganizationFactory.create(sam_gov_entity__uei=sam_uei),
        )
        ApplicationFormFactory.create(
            application=application,
            competition_form=source_competition_form,
            application_response={},
        )
        budget_application_form = ApplicationFormFactory.create(
            application=application,
            competition_form=budget_competition_form,
            application_response={},
        )
        user = _user_with_modify_access(application)

        update_application_form(
            db_session,
            application.application_id,
            source_form.form_id,
            user,
            application_response={"applicant_info": {"organization_info": {"sam_uei": sam_uei}}},
        )
        db_session.commit()

        db_session.expire_all()
        populated = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == budget_application_form.application_form_id
            )
        ).scalar_one()
        assert populated.application_response == {"samuei": sam_uei}
    finally:
        restore_runtime_form_after_test(source_key, previous_source)
        restore_runtime_form_after_test(budget_key, previous_budget)

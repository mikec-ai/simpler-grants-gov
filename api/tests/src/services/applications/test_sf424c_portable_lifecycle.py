"""DB-backed lifecycle gates for the unregistered portable SF-424C form."""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any

from grants_shared.util.datetime_util import get_now_us_eastern_date
from sqlalchemy import select

from src.constants.lookup_constants import ApplicationStatus, Privilege
from src.db.models.competition_models import ApplicationForm
from src.services.applications.submit_application import submit_application
from src.services.applications.update_application_form import update_application_form
from tests.src.db.models.factories import (
    ApplicationFactory,
    ApplicationFormFactory,
    ApplicationUserFactory,
    ApplicationUserRoleFactory,
    CompetitionFactory,
    CompetitionFormFactory,
    RoleFactory,
    UserFactory,
)
from tests.src.form_schema.form_spec.lifecycle import (
    register_runtime_form_for_test,
    restore_runtime_form_after_test,
)
from tests.src.form_schema.form_spec.test_sf424c_portable import calculated_response, input_response


def _link_user(application: Any, privileges: list[Privilege]) -> Any:
    user = UserFactory.create()
    ApplicationUserRoleFactory.create(
        application_user=ApplicationUserFactory.create(user=user, application=application),
        role=RoleFactory.create(privileges=privileges, is_application_role=True),
    )
    return user


def test_sf424c_save_reload_materializes_all_calculated_outputs(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key, previous = register_runtime_form_for_test("sf424c")
    try:
        competition = CompetitionFactory.create(competition_forms=[])
        competition_form = CompetitionFormFactory.create(competition=competition, form=form)
        application = ApplicationFactory.create(competition=competition)
        application_form = ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response={},
        )
        user = _link_user(application, [Privilege.MODIFY_APPLICATION])

        with db_session.begin():
            saved, warnings = update_application_form(
                db_session,
                application.application_id,
                form.form_id,
                user,
                application_response=input_response(),
            )

        assert warnings == []
        assert saved.application_response == calculated_response()
        db_session.expire(saved)
        reloaded = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == application_form.application_form_id
            )
        ).scalar_one()
        assert reloaded.application_response == calculated_response()
    finally:
        restore_runtime_form_after_test(registry_key, previous)


def test_sf424c_calculated_response_passes_submission_lifecycle(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key, previous = register_runtime_form_for_test("sf424c")
    try:
        competition = CompetitionFactory.create(
            closing_date=get_now_us_eastern_date() + timedelta(days=1),
            grace_period=3,
            competition_forms=[],
        )
        competition_form = CompetitionFormFactory.create(competition=competition, form=form)
        application = ApplicationFactory.create(
            competition=competition,
            application_status=ApplicationStatus.IN_PROGRESS,
        )
        user = _link_user(application, [Privilege.SUBMIT_APPLICATION])
        ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response=copy.deepcopy(calculated_response()),
        )

        with db_session.begin():
            submitted = submit_application(db_session, application.application_id, user)

        assert submitted.application_status is ApplicationStatus.SUBMITTED
        assert submitted.submitted_by == user.user_id
    finally:
        restore_runtime_form_after_test(registry_key, previous)

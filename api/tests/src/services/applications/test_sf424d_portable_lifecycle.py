"""DB-backed lifecycle gates for the unregistered portable SF-424D profiles."""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any

import pytest
from grants_shared.util.datetime_util import get_now_us_eastern_date
from sqlalchemy import select

from src.constants.lookup_constants import ApplicationStatus, Privilege
from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.registry.form_template_registry import FormTemplateKey, form_template_registry
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
from tests.src.form_schema.form_spec.test_sf424d_portable import RELEASABLE_PROFILES, VALID_RESPONSE


def _register_runtime_form(form_id: str) -> tuple[Any, FormTemplateKey]:
    form = build_runtime_form(form_id)
    key = FormTemplateKey(form.form_id, 1)
    form_template_registry.register(form, major_version=1)
    return form, key


def _link_user(application: Any, privileges: list[Privilege]) -> Any:
    user = UserFactory.create(email="portable-reviewer@example.com")
    ApplicationUserRoleFactory.create(
        application_user=ApplicationUserFactory.create(user=user, application=application),
        role=RoleFactory.create(privileges=privileges, is_application_role=True),
    )
    return user


@pytest.mark.parametrize("form_id", RELEASABLE_PROFILES)
def test_sf424d_profile_save_and_reload(
    enable_factory_create: Any,
    db_session: Any,
    form_id: str,
) -> None:
    form, registry_key = _register_runtime_form(form_id)
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
                application_response=copy.deepcopy(VALID_RESPONSE),
            )

        assert warnings == []
        db_session.expire(saved)
        reloaded = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == application_form.application_form_id
            )
        ).scalar_one()
        assert reloaded.application_response == VALID_RESPONSE
    finally:
        form_template_registry._registry.pop(registry_key, None)


@pytest.mark.parametrize("form_id", RELEASABLE_PROFILES)
def test_sf424d_profile_submission_records_acceptance_event(
    enable_factory_create: Any,
    db_session: Any,
    form_id: str,
) -> None:
    form, registry_key = _register_runtime_form(form_id)
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
        application_form = ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response=copy.deepcopy(VALID_RESPONSE),
        )

        with db_session.begin():
            submitted = submit_application(db_session, application.application_id, user)

        assert submitted.application_status is ApplicationStatus.SUBMITTED
        assert submitted.submitted_by == user.user_id
        assert application_form.application_response["signature"] == user.email
        assert len(application_form.application_response["date_signed"].split("-")) == 3
    finally:
        form_template_registry._registry.pop(registry_key, None)

"""DB-backed lifecycle canary for portable SF-LLL without production registration."""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any

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
    LinkExternalUserFactory,
    RoleFactory,
    UserFactory,
)
from tests.src.form_schema.form_spec.test_sflll_portable import VALID_RESPONSE


def _register_runtime_form() -> tuple[Any, FormTemplateKey, Any | None]:
    form = build_runtime_form("sflll")
    key = FormTemplateKey(form.form_id, 1)
    previous = form_template_registry._registry.pop(key, None)
    try:
        form_template_registry.register(form, major_version=1)
    except Exception:
        if previous is not None:
            form_template_registry._registry[key] = previous
        raise
    return form, key, previous


def _restore_runtime_form(key: FormTemplateKey, previous: Any | None) -> None:
    form_template_registry._registry.pop(key, None)
    if previous is not None:
        form_template_registry._registry[key] = previous


def _link_user(application: Any, privileges: list[Privilege]) -> Any:
    user = UserFactory.create()
    LinkExternalUserFactory.create(user=user, email="portable-reviewer@example.com")
    ApplicationUserRoleFactory.create(
        application_user=ApplicationUserFactory.create(user=user, application=application),
        role=RoleFactory.create(privileges=privileges, is_application_role=True),
    )
    return user


def test_sflll_save_and_reload_preserves_repeated_service_individuals(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key, previous = _register_runtime_form()
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
        response = copy.deepcopy(VALID_RESPONSE)
        response["individuals_performing_services"].append({
            "name": {"first_name": "Katherine", "last_name": "Johnson"}
        })

        with db_session.begin():
            saved, warnings = update_application_form(
                db_session,
                application.application_id,
                form.form_id,
                user,
                application_response=response,
            )

        assert warnings == []
        db_session.expire(saved)
        reloaded = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == application_form.application_form_id
            )
        ).scalar_one()
        assert reloaded.application_response == response
    finally:
        _restore_runtime_form(registry_key, previous)


def test_sflll_submission_populates_signature_and_completes_application(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key, previous = _register_runtime_form()
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
        signature = application_form.application_response["signature_block"]
        assert signature["signature"] == user.email
        assert len(signature["signed_date"].split("-")) == 3
    finally:
        _restore_runtime_form(registry_key, previous)

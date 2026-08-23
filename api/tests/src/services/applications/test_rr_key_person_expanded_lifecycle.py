"""DB-backed lifecycle canary for the vendored R&R Key Person form.

These tests prove Simpler's ordinary application services can persist and validate the
portable package. They deliberately do not register the form for production release.
"""

import copy
from datetime import timedelta
from typing import Any

from grants_shared.util.datetime_util import get_now_us_eastern_date
from sqlalchemy import select

from src.constants.lookup_constants import (
    ApplicationAuditEvent,
    ApplicationStatus,
    Privilege,
)
from src.db.models.competition_models import ApplicationAudit, ApplicationForm
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.registry.form_template_registry import (
    FormTemplateKey,
    form_template_registry,
)
from src.services.applications.submit_application import submit_application
from src.services.applications.update_application_form import update_application_form
from tests.src.db.models.factories import (
    ApplicationAttachmentFactory,
    ApplicationFactory,
    ApplicationFormFactory,
    ApplicationUserFactory,
    ApplicationUserRoleFactory,
    CompetitionFactory,
    CompetitionFormFactory,
    RoleFactory,
    UserFactory,
)
from tests.src.form_schema.form_spec.test_rr_key_person_expanded_portable import (
    ADDITIONAL_BIOGRAPHICAL_SKETCHES,
    ADDITIONAL_CURRENT_SUPPORT,
    ADDITIONAL_PROFILES,
    ATTACHMENT_IDS,
    VALID_RESPONSE,
)


def _register_runtime_form() -> tuple[Any, FormTemplateKey]:
    form = build_runtime_form("rr-key-person-expanded")
    key = FormTemplateKey(form.form_id, 1)
    form_template_registry.register(form, major_version=1)
    return form, key


def _link_user(application: Any, privileges: list[Privilege]) -> Any:
    user = UserFactory.create()
    ApplicationUserRoleFactory.create(
        application_user=ApplicationUserFactory.create(user=user, application=application),
        role=RoleFactory.create(privileges=privileges, is_application_role=True),
    )
    return user


def _create_response_attachments(application: Any, user: Any) -> dict[str, str]:
    attachment_ids: dict[str, str] = {}
    for source_id in ATTACHMENT_IDS:
        attachment = ApplicationAttachmentFactory.create(
            application=application,
            user=user,
        )
        attachment_ids[source_id] = str(attachment.application_attachment_id)
    return attachment_ids


def _response_with_attachment_ids(attachment_ids: dict[str, str]) -> dict[str, Any]:
    def replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace(child) for key, child in value.items()}
        if isinstance(value, list):
            return [replace(child) for child in value]
        if isinstance(value, str):
            return attachment_ids.get(value, value)
        return value

    return replace(copy.deepcopy(VALID_RESPONSE))


def test_key_person_save_reload_and_nested_attachment_audit(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key = _register_runtime_form()
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
        attachment_ids = _create_response_attachments(application, user)

        response = _response_with_attachment_ids(attachment_ids)
        added_person = {
            **response["senior_key_persons"][0],
            "name": {"first_name": "Morgan", "last_name": "Mentor"},
        }
        added_person.pop("biographical_sketch")
        added_person.pop("current_pending_support")
        response["senior_key_persons"].append(added_person)
        response["senior_key_persons"][0]["department"] = "Biomedical Informatics"

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

        attachment_audits = db_session.execute(
            select(ApplicationAudit).where(
                ApplicationAudit.application_id == application.application_id,
                ApplicationAudit.application_audit_event == ApplicationAuditEvent.ATTACHMENT_ADDED,
            )
        ).scalars()
        assert {str(audit.target_attachment_id) for audit in attachment_audits} == set(
            attachment_ids.values()
        )
    finally:
        form_template_registry._registry.pop(registry_key, None)


def test_key_person_valid_response_passes_application_submit_service(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key = _register_runtime_form()
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
        attachment_ids = _create_response_attachments(application, user)
        ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response=_response_with_attachment_ids(attachment_ids),
        )

        with db_session.begin():
            submitted = submit_application(db_session, application.application_id, user)

        assert submitted.application_status is ApplicationStatus.SUBMITTED
        assert submitted.submitted_by == user.user_id
        db_session.refresh(application)
        assert application.application_status is ApplicationStatus.SUBMITTED
    finally:
        form_template_registry._registry.pop(registry_key, None)


def test_key_person_attachment_overflow_ids_are_audited_on_save(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    """The three top-level capture fields use the same save-time audit path."""

    form, registry_key = _register_runtime_form()
    try:
        competition = CompetitionFactory.create(competition_forms=[])
        CompetitionFormFactory.create(competition=competition, form=form)
        application = ApplicationFactory.create(competition=competition)
        user = _link_user(application, [Privilege.MODIFY_APPLICATION])
        attachment_ids = _create_response_attachments(application, user)

        response = {
            "additional_profiles": attachment_ids[ADDITIONAL_PROFILES],
            "additional_biographical_sketches": attachment_ids[ADDITIONAL_BIOGRAPHICAL_SKETCHES],
            "additional_current_pending_support": attachment_ids[ADDITIONAL_CURRENT_SUPPORT],
        }
        with db_session.begin():
            update_application_form(
                db_session,
                application.application_id,
                form.form_id,
                user,
                application_response=response,
            )

        audits = db_session.execute(
            select(ApplicationAudit).where(
                ApplicationAudit.application_id == application.application_id,
                ApplicationAudit.application_audit_event == ApplicationAuditEvent.ATTACHMENT_ADDED,
            )
        ).scalars()
        assert {str(audit.target_attachment_id) for audit in audits} == {
            attachment_ids[ADDITIONAL_PROFILES],
            attachment_ids[ADDITIONAL_BIOGRAPHICAL_SKETCHES],
            attachment_ids[ADDITIONAL_CURRENT_SUPPORT],
        }
    finally:
        form_template_registry._registry.pop(registry_key, None)

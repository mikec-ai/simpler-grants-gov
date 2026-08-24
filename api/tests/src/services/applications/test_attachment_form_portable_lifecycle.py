"""DB-backed handoff evidence for the unregistered portable Attachment Form.

The tests use Simpler's ordinary update, audit, validation, and submission services.
They do not register the portable package for production or claim human review.
"""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any

import pytest
from apiflask.exceptions import HTTPError
from grants_shared.util.datetime_util import get_now_us_eastern_date
from sqlalchemy import select

from src.constants.lookup_constants import (
    ApplicationAuditEvent,
    ApplicationStatus,
    Privilege,
)
from src.db.models.competition_models import ApplicationAudit, ApplicationForm
from src.form_schema.form_spec.preview import build_preview_form
from src.form_schema.registry.form_template_registry import (
    FormTemplateKey,
    form_template_registry,
)
from src.services.applications.submit_application import submit_application
from src.services.applications.update_application_form import update_application_form
from src.validation.validation_constants import ValidationErrorType
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
from tests.src.form_schema.form_spec.lifecycle import restore_runtime_form_after_test


def _link_user(application: Any, privileges: list[Privilege]) -> Any:
    user = UserFactory.create()
    ApplicationUserRoleFactory.create(
        application_user=ApplicationUserFactory.create(user=user, application=application),
        role=RoleFactory.create(privileges=privileges, is_application_role=True),
    )
    return user


def _register_preview_form() -> tuple[Any, FormTemplateKey, Any | None]:
    """Register the banked-only package under its lower-environment preview ID."""

    form = build_preview_form("attachment-form")
    key = FormTemplateKey(form.form_id, 1)
    previous = form_template_registry._registry.pop(key, None)
    form_template_registry.register(form, major_version=1)
    return form, key, previous


def test_attachment_form_save_reload_replacement_removal_and_audit(
    enable_factory_create: Any,
    db_session: Any,
    s3_config: Any,
) -> None:
    form, registry_key, previous = _register_preview_form()
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
        original_by_slot = {
            slot: ApplicationAttachmentFactory.create(application=application, user=user)
            for slot in (1, 5, 15)
        }
        sparse_response = {
            f"att{slot}": str(attachment.application_attachment_id)
            for slot, attachment in original_by_slot.items()
        }
        replacement = ApplicationAttachmentFactory.create(application=application, user=user)
        replacement_id = str(replacement.application_attachment_id)
        replacement_response = {
            "att1": replacement_id,
            "att15": sparse_response["att15"],
        }

        saved, warnings = update_application_form(
            db_session,
            application.application_id,
            form.form_id,
            user,
            application_response=copy.deepcopy(sparse_response),
        )
        db_session.commit()

        assert warnings == []
        db_session.expire(saved)
        reloaded = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == application_form.application_form_id
            )
        ).scalar_one()
        assert reloaded.application_response == sparse_response
        db_session.commit()

        saved, warnings = update_application_form(
            db_session,
            application.application_id,
            form.form_id,
            user,
            application_response=copy.deepcopy(replacement_response),
        )
        db_session.commit()

        assert warnings == []
        db_session.expire(saved)
        reloaded = db_session.execute(
            select(ApplicationForm).where(
                ApplicationForm.application_form_id == application_form.application_form_id
            )
        ).scalar_one()
        assert reloaded.application_response == replacement_response

        for attachment in original_by_slot.values():
            db_session.refresh(attachment)
        assert original_by_slot[1].is_deleted is True
        assert original_by_slot[5].is_deleted is True
        assert original_by_slot[15].is_deleted is False

        audits = db_session.execute(
            select(ApplicationAudit).where(
                ApplicationAudit.application_id == application.application_id,
                ApplicationAudit.application_audit_event.in_(
                    [
                        ApplicationAuditEvent.ATTACHMENT_ADDED,
                        ApplicationAuditEvent.ATTACHMENT_DELETED,
                    ]
                ),
            )
        ).scalars()
        events = {
            (audit.application_audit_event, str(audit.target_attachment_id)) for audit in audits
        }
        assert events == {
            *{
                (ApplicationAuditEvent.ATTACHMENT_ADDED, attachment_id)
                for attachment_id in sparse_response.values()
            },
            (ApplicationAuditEvent.ATTACHMENT_ADDED, replacement_id),
            (ApplicationAuditEvent.ATTACHMENT_DELETED, sparse_response["att1"]),
            (ApplicationAuditEvent.ATTACHMENT_DELETED, sparse_response["att5"]),
        }
    finally:
        restore_runtime_form_after_test(registry_key, previous)


def test_attachment_form_rejects_foreign_attachment_ownership(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key, previous = _register_preview_form()
    try:
        competition = CompetitionFactory.create(competition_forms=[])
        competition_form = CompetitionFormFactory.create(competition=competition, form=form)
        application = ApplicationFactory.create(competition=competition)
        ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response={},
        )
        user = _link_user(application, [Privilege.MODIFY_APPLICATION])
        foreign_attachment = ApplicationAttachmentFactory.create(
            application=ApplicationFactory.create()
        )

        with db_session.begin():
            _, warnings = update_application_form(
                db_session,
                application.application_id,
                form.form_id,
                user,
                application_response={"att1": str(foreign_attachment.application_attachment_id)},
            )

        assert len(warnings) == 1
        assert warnings[0].type == ValidationErrorType.UNKNOWN_APPLICATION_ATTACHMENT
        assert warnings[0].field == "$.att1"
        attachment_audits = db_session.execute(
            select(ApplicationAudit).where(
                ApplicationAudit.application_id == application.application_id,
                ApplicationAudit.application_audit_event == ApplicationAuditEvent.ATTACHMENT_ADDED,
            )
        ).scalars()
        assert list(attachment_audits) == []
    finally:
        restore_runtime_form_after_test(registry_key, previous)


def test_attachment_form_submission_locks_further_updates(
    enable_factory_create: Any,
    db_session: Any,
) -> None:
    form, registry_key, previous = _register_preview_form()
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
        user = _link_user(
            application,
            [Privilege.MODIFY_APPLICATION, Privilege.SUBMIT_APPLICATION],
        )
        attachment = ApplicationAttachmentFactory.create(application=application, user=user)
        attachment_id = str(attachment.application_attachment_id)
        ApplicationFormFactory.create(
            application=application,
            competition_form=competition_form,
            application_response={"att1": attachment_id},
        )

        with db_session.begin():
            submitted = submit_application(db_session, application.application_id, user)

        assert submitted.application_status is ApplicationStatus.SUBMITTED
        assert submitted.submitted_by == user.user_id

        with pytest.raises(HTTPError) as error:
            with db_session.begin():
                update_application_form(
                    db_session,
                    application.application_id,
                    form.form_id,
                    user,
                    application_response={},
                )
        assert error.value.status_code == 403
        assert error.value.message is not None
        assert "Cannot modify application" in error.value.message
    finally:
        restore_runtime_form_after_test(registry_key, previous)

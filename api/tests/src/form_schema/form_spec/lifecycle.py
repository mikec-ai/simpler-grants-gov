"""Reusable lifecycle conformance checks for portable form packages.

These checks deliberately execute Simpler's ordinary validation and rule-processing
boundary. They are not a second form runtime and contain no form-specific semantics.
Each form test supplies only representative responses and expected validation fields.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

from src.constants.lookup_constants import ApplicationFormStatus
from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.registry.form_template_registry import FormTemplateRegistry
from src.services.applications.application_validation import (
    ApplicationAction,
    validate_application_form,
)


@dataclass(frozen=True)
class ValidationCase:
    """One response mutation and the JSON paths it must make invalid."""

    name: str
    response: dict[str, Any]
    expected_fields: frozenset[str]


def application_form_for(
    form_id: str,
    response: dict[str, Any],
    *,
    submitter_email: str = "reviewer@example.gov",
) -> ApplicationForm:
    """Build the smallest object graph needed by Simpler's real form lifecycle."""

    form = build_runtime_form(form_id)
    # Exercise the same registration boundary production uses. Registration resolves
    # the pinned local question-bank graph, so validation never performs a network fetch.
    registry = FormTemplateRegistry()
    registry.register(form, major_version=1)
    application = SimpleNamespace(
        submitted_by_user=SimpleNamespace(email=submitter_email),
        application_attachments=[],
    )
    return cast(
        ApplicationForm,
        SimpleNamespace(
            application_response=copy.deepcopy(response),
            application=application,
            application_form_id=f"{form_id}-lifecycle-test",
            form_id=form.form_id,
            form=form,
            competition_form=SimpleNamespace(is_required=True),
            application_form_status=ApplicationFormStatus.IN_PROGRESS,
        ),
    )


def assert_json_round_trip(response: dict[str, Any]) -> None:
    """Assert the response survives the JSON persistence boundary byte-for-byte."""

    assert json.loads(json.dumps(response, sort_keys=True)) == response


def assert_validation_case(form_id: str, case: ValidationCase) -> None:
    """Execute a validation vector through Simpler's GET lifecycle."""

    application_form = application_form_for(form_id, case.response)
    errors = validate_application_form(application_form, ApplicationAction.GET)

    assert {error.field for error in errors} == case.expected_fields, case.name
    expected_status = (
        ApplicationFormStatus.IN_PROGRESS
        if case.expected_fields
        else ApplicationFormStatus.COMPLETE
    )
    assert application_form.application_form_status is expected_status


def submit_form(form_id: str, response: dict[str, Any]) -> ApplicationForm:
    """Execute submit-time population and validation for a portable form."""

    application_form = application_form_for(form_id, response)
    errors = validate_application_form(application_form, ApplicationAction.SUBMIT)

    assert errors == []
    assert application_form.application_form_status is ApplicationFormStatus.COMPLETE
    return application_form

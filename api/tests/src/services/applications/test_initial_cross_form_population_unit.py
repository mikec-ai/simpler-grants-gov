"""Database-independent tests for portable initial cross-form population."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.services.applications.apply_initial_population import (
    apply_initial_population_from_source_update,
)


def _session_with_modified_targets(*target_ids: uuid.UUID) -> Mock:
    session = Mock()
    session.execute.return_value.scalars.return_value.all.return_value = list(target_ids)
    return session


def _forms(source_response: dict, target_response: dict | None = None) -> tuple[object, object]:
    source = SimpleNamespace(
        application_form_id=uuid.uuid4(),
        form_id=runtime_identity("rr-sf424").form_id,
        application_response=source_response,
    )
    target = SimpleNamespace(
        application_form_id=uuid.uuid4(),
        form_id=runtime_identity("rr-budget").form_id,
        application_response=target_response or {},
    )
    return source, target


def test_exact_source_values_populate_declared_budget_targets() -> None:
    source, target = _forms(
        {
            "applicant_info": {
                "organization_info": {
                    "sam_uei": "ABCDEFGHIJKL",
                    "organization_name": "Example Research University",
                }
            },
            "proposed_project_period": {"proposed_start_date": "2027-07-01"},
        }
    )
    application = SimpleNamespace(application_id=uuid.uuid4(), application_forms=[source, target])

    changed = apply_initial_population_from_source_update(
        _session_with_modified_targets(), application, source
    )

    assert changed == (target,)
    assert target.application_response == {
        "samuei": "ABCDEFGHIJKL",
        "organization_name": "Example Research University",
        "budget_year": [{"budget_period_start_date": "2027-07-01"}],
    }


def test_missing_sources_are_skipped_and_modified_target_is_never_overwritten() -> None:
    source, target = _forms(
        {"applicant_info": {"organization_info": {"sam_uei": "ABCDEFGHIJKL"}}},
        {"organization_name": "Applicant-confirmed Organization"},
    )
    application = SimpleNamespace(application_id=uuid.uuid4(), application_forms=[source, target])

    changed = apply_initial_population_from_source_update(
        _session_with_modified_targets(target.application_form_id), application, source
    )

    assert changed == ()
    assert target.application_response == {"organization_name": "Applicant-confirmed Organization"}

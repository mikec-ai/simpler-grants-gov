"""Apply portable cross-form initial values without overwriting applicant work."""

from __future__ import annotations

import copy
import logging
from typing import Any

import grants_shared.adapters.db as db
from sqlalchemy import select

from src.constants.lookup_constants import ApplicationAuditEvent
from src.db.models.competition_models import Application, ApplicationAudit, ApplicationForm
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.operational_behavior import ProjectedOperationalBehavior
from src.form_schema.form_spec.preview import operational_behavior_for_preview_form_id
from src.form_schema.form_spec.runtime_identity import portable_id_for_runtime_form_id

logger = logging.getLogger(__name__)

_MISSING = object()


def _tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError(f"response pointer must be absolute: {pointer!r}")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


def _value_at(response: dict[str, Any], pointer: str) -> Any:
    current: Any = response
    for token in _tokens(pointer):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return _MISSING
    return current


def _selected_target_pointer(behavior: ProjectedOperationalBehavior) -> str:
    selection = behavior.target_selection
    if selection is None:
        if "/[]/" in behavior.path:
            raise ValueError(f"operational target {behavior.path!r} requires an array selection")
        return behavior.path
    prefix = f"{selection.array_path}/[]/"
    if not behavior.path.startswith(prefix):
        raise ValueError(
            f"operational target {behavior.path!r} is outside selected array "
            f"{selection.array_path!r}"
        )
    return f"{selection.array_path}/{selection.index}/{behavior.path.removeprefix(prefix)}"


def _set_value(response: dict[str, Any], pointer: str, value: Any) -> bool:
    tokens = _tokens(pointer)
    if not tokens:
        return False
    current: Any = response
    for index, token in enumerate(tokens[:-1]):
        next_is_index = tokens[index + 1].isdigit()
        if isinstance(current, dict):
            child = current.get(token)
            if child is None:
                child = [] if next_is_index else {}
                current[token] = child
            if not isinstance(child, (dict, list)):
                return False
            current = child
        elif isinstance(current, list) and token.isdigit():
            item_index = int(token)
            while len(current) <= item_index:
                current.append({})
            child = current[item_index]
            if not isinstance(child, (dict, list)):
                return False
            current = child
        else:
            return False

    final = tokens[-1]
    if isinstance(current, dict):
        current[final] = copy.deepcopy(value)
        return True
    if isinstance(current, list) and final.isdigit():
        item_index = int(final)
        while len(current) <= item_index:
            current.append(None)
        current[item_index] = copy.deepcopy(value)
        return True
    return False


def apply_initial_population_from_source_update(
    db_session: db.Session,
    application: Application,
    source_form: ApplicationForm,
) -> tuple[ApplicationForm, ...]:
    """Apply matching portable values until each target receives its first user update."""

    modified_target_ids = set(
        db_session.execute(
            select(ApplicationAudit.target_application_form_id).where(
                ApplicationAudit.application_id == application.application_id,
                ApplicationAudit.application_audit_event == ApplicationAuditEvent.FORM_UPDATED,
                ApplicationAudit.target_application_form_id.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    changed: list[ApplicationForm] = []
    for target_form in application.application_forms:
        if (
            target_form.application_form_id == source_form.application_form_id
            or target_form.application_form_id in modified_target_ids
        ):
            continue
        portable_id = portable_id_for_runtime_form_id(target_form.form_id)
        available_behaviors = (
            load_form(portable_id).operational_behavior
            if portable_id is not None
            else operational_behavior_for_preview_form_id(target_form.form_id)
        )
        behaviors = tuple(
            behavior
            for behavior in available_behaviors
            if behavior.value_source.runtime_form_id == source_form.form_id
            and behavior.execution_policy.trigger == "source-response-updated"
            and behavior.execution_policy.write_policy == "until-target-user-modified"
            and behavior.execution_policy.missing_source_policy == "skip"
        )
        if not behaviors:
            continue

        response = copy.deepcopy(target_form.application_response or {})
        target_changed = False
        for behavior in behaviors:
            source_value = _value_at(
                source_form.application_response or {}, behavior.value_source.path
            )
            if source_value is _MISSING or source_value is None:
                continue
            target_pointer = _selected_target_pointer(behavior)
            if not _set_value(response, target_pointer, source_value):
                logger.warning(
                    "Skipped portable initial population because the target response shape conflicts",
                    extra={
                        "application_id": application.application_id,
                        "source_form_id": source_form.form_id,
                        "target_form_id": target_form.form_id,
                        "target_pointer": target_pointer,
                    },
                )
                continue
            target_changed = True

        if target_changed:
            target_form.application_response = response
            changed.append(target_form)

    return tuple(changed)

"""Project portable operational behavior into Simpler runtime coordinates."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from typing import Any, Literal, cast

from src.form_schema.form_spec.projection import Projection, project_response_pointer


@dataclasses.dataclass(frozen=True)
class ProjectedCanonicalValueSource:
    form_id: str
    runtime_form_id: uuid.UUID
    canonical_path: str
    path: str


@dataclasses.dataclass(frozen=True)
class ProjectedTargetSelection:
    array_path: str
    index: int


@dataclasses.dataclass(frozen=True)
class ProjectedExecutionPolicy:
    trigger: Literal["source-response-updated"]
    write_policy: Literal["until-target-user-modified"]
    missing_source_policy: Literal["skip"]


@dataclasses.dataclass(frozen=True)
class ProjectedOperationalBehavior:
    canonical_path: str
    path: str
    operation_kind: Literal["prefill"]
    editability: Literal["editable", "read-only", "protected", "not-applicable", "unspecified"]
    execution_policy: ProjectedExecutionPolicy
    value_source: ProjectedCanonicalValueSource
    target_selection: ProjectedTargetSelection | None


ProjectionFor = Callable[[str], Projection]
RuntimeFormIdFor = Callable[[str], uuid.UUID]

Editability = Literal["editable", "read-only", "protected", "not-applicable", "unspecified"]

_EDITABILITY = {"editable", "read-only", "protected", "not-applicable", "unspecified"}


def _required_string(record: dict[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} requires non-empty {key}")
    return value


def project_operational_behavior(
    document: dict[str, Any],
    *,
    form_id: str,
    target_projection: Projection,
    projection_for: ProjectionFor,
    runtime_form_id_for: RuntimeFormIdFor,
) -> tuple[ProjectedOperationalBehavior, ...]:
    """Project exact canonical coordinates from the closed portable runtime contract."""

    if document.get("contract") != "grants-form-operational-behavior/v1":
        raise ValueError(f"{form_id}: unsupported operational behavior contract")
    if document.get("formId") != form_id:
        raise ValueError(f"{form_id}: operational behavior identity does not match form")
    records = document.get("behaviors")
    if not isinstance(records, list):
        raise ValueError(f"{form_id}: operational behaviors must be an array")

    projected: list[ProjectedOperationalBehavior] = []
    for index, record in enumerate(records):
        context = f"{form_id}: operational behavior {index}"
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be an object")
        canonical_path = _required_string(record, "canonicalPath", context)
        if not canonical_path.startswith("/"):
            raise ValueError(f"{context} canonicalPath must be an absolute JSON pointer")
        operation_kind = record.get("operationKind")
        if operation_kind != "prefill":
            raise ValueError(f"{context} has unsupported operation kind {operation_kind!r}")
        editability = record.get("editability")
        if editability not in _EDITABILITY:
            raise ValueError(f"{context} has unsupported editability {editability!r}")
        value_source = record.get("valueSource")
        if not isinstance(value_source, dict):
            raise ValueError(f"{context} valueSource must be an object")
        if value_source.get("kind") == "canonical":
            source_form_id = _required_string(value_source, "blockId", context)
            source_path = _required_string(value_source, "path", context)
            if not source_path.startswith("/"):
                raise ValueError(f"{context} source path must be an absolute JSON pointer")
            projected_source = ProjectedCanonicalValueSource(
                form_id=source_form_id,
                runtime_form_id=runtime_form_id_for(source_form_id),
                canonical_path=source_path,
                path=project_response_pointer(source_path, projection_for(source_form_id)),
            )
        else:
            raise ValueError(f"{context} has unsupported valueSource kind")

        execution_policy = record.get("executionPolicy")
        if not isinstance(execution_policy, dict):
            raise ValueError(f"{context} executionPolicy must be an object")
        if execution_policy.get("trigger") != "source-response-updated":
            raise ValueError(f"{context} has unsupported execution trigger")
        if execution_policy.get("writePolicy") != "until-target-user-modified":
            raise ValueError(f"{context} has unsupported write policy")
        if execution_policy.get("missingSourcePolicy") != "skip":
            raise ValueError(f"{context} has unsupported missing-source policy")

        selection = record.get("targetSelection")
        projected_selection: ProjectedTargetSelection | None = None
        if selection is not None:
            if not isinstance(selection, dict):
                raise ValueError(f"{context} targetSelection must be an object")
            array_path = _required_string(selection, "arrayPath", context)
            selected_index = selection.get("index")
            if (
                not isinstance(selected_index, int)
                or isinstance(selected_index, bool)
                or selected_index < 0
            ):
                raise ValueError(f"{context} targetSelection index must be a non-negative integer")
            projected_selection = ProjectedTargetSelection(
                array_path=project_response_pointer(array_path, target_projection),
                index=selected_index,
            )

        projected.append(
            ProjectedOperationalBehavior(
                canonical_path=canonical_path,
                path=project_response_pointer(canonical_path, target_projection),
                operation_kind="prefill",
                editability=cast(Editability, editability),
                execution_policy=ProjectedExecutionPolicy(
                    trigger="source-response-updated",
                    write_policy="until-target-user-modified",
                    missing_source_policy="skip",
                ),
                value_source=projected_source,
                target_selection=projected_selection,
            )
        )
    return tuple(projected)

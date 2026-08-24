"""Project portable operational evidence into Simpler runtime coordinates.

Evidence remains non-executable.  This module gives a future application-lifecycle service a
typed, fail-closed adapter boundary without teaching that service canonical naming or making an
evidence sidecar itself the runtime rule engine.
"""

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
class ProjectedExternalValueSource:
    namespace: str
    path: str


@dataclasses.dataclass(frozen=True)
class ProjectedTargetSelection:
    array_path: str
    index: int


@dataclasses.dataclass(frozen=True)
class ProjectedOperationalBehavior:
    canonical_path: str
    path: str
    operation_kind: Literal["prefill", "external-derived", "discard", "replace"]
    editability: Literal["editable", "read-only", "protected", "not-applicable", "unspecified"]
    authority: Literal["official_source", "implementation_parity", "unresolved"]
    execution_status: Literal["source-bound-uncompiled"]
    value_source: ProjectedCanonicalValueSource | ProjectedExternalValueSource | None
    target_selection: ProjectedTargetSelection | None
    source_id: str | None
    source_path: str | None
    source_record: str | None


ProjectionFor = Callable[[str], Projection]
RuntimeFormIdFor = Callable[[str], uuid.UUID]

OperationKind = Literal["prefill", "external-derived", "discard", "replace"]
Editability = Literal["editable", "read-only", "protected", "not-applicable", "unspecified"]
Authority = Literal["official_source", "implementation_parity", "unresolved"]

_OPERATION_KINDS = {"prefill", "external-derived", "discard", "replace"}
_EDITABILITY = {"editable", "read-only", "protected", "not-applicable", "unspecified"}
_AUTHORITIES = {"official_source", "implementation_parity", "unresolved"}


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
    """Project exact canonical coordinates while preserving the non-executable boundary."""

    if document.get("contract") != "grants-form-evidence/v1":
        raise ValueError(f"{form_id}: unsupported operational evidence contract")
    block = document.get("block")
    if not isinstance(block, dict) or block.get("id") != form_id or block.get("kind") != "form":
        raise ValueError(f"{form_id}: operational evidence block identity does not match form")
    records = document.get("operationalBehaviorEvidence", [])
    if not isinstance(records, list):
        raise ValueError(f"{form_id}: operationalBehaviorEvidence must be an array")

    projected: list[ProjectedOperationalBehavior] = []
    for index, record in enumerate(records):
        context = f"{form_id}: operational behavior {index}"
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be an object")
        canonical_path = _required_string(record, "canonicalPath", context)
        if not canonical_path.startswith("/"):
            raise ValueError(f"{context} canonicalPath must be an absolute JSON pointer")
        execution_status = record.get("executionStatus")
        if execution_status != "source-bound-uncompiled":
            raise ValueError(f"{context} has unsupported execution status {execution_status!r}")
        operation_kind = record.get("operationKind")
        if operation_kind not in _OPERATION_KINDS:
            raise ValueError(f"{context} has unsupported operation kind {operation_kind!r}")
        editability = record.get("editability")
        if editability not in _EDITABILITY:
            raise ValueError(f"{context} has unsupported editability {editability!r}")
        authority = record.get("authority")
        if authority not in _AUTHORITIES:
            raise ValueError(f"{context} has unsupported authority {authority!r}")

        value_source = record.get("valueSource")
        projected_source: ProjectedCanonicalValueSource | ProjectedExternalValueSource | None
        if value_source is None:
            projected_source = None
        elif not isinstance(value_source, dict):
            raise ValueError(f"{context} valueSource must be an object")
        elif value_source.get("kind") == "canonical":
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
        elif value_source.get("kind") == "external":
            projected_source = ProjectedExternalValueSource(
                namespace=_required_string(value_source, "namespace", context),
                path=_required_string(value_source, "path", context),
            )
        else:
            raise ValueError(f"{context} has unsupported valueSource kind")

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
                operation_kind=cast(OperationKind, operation_kind),
                editability=cast(Editability, editability),
                authority=cast(Authority, authority),
                execution_status=execution_status,
                value_source=projected_source,
                target_selection=projected_selection,
                source_id=record.get("sourceId"),
                source_path=record.get("sourcePath"),
                source_record=record.get("sourceRecord"),
            )
        )
    return tuple(projected)

"""Simpler-owned runtime identity for portable forms.

Portable form ids join this target data to producer artifacts. UUIDs and ``FormType``
values are generated and interpreted by Simpler, so they do not belong in portable
``FormMeta``.
"""

from __future__ import annotations

import functools
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUNTIME_IDENTITIES = Path(__file__).with_name("runtime-identities.json")
RUNTIME_IDENTITY_CONTRACT = "sgg-form-runtime-identities/v1"
RUNTIME_IDENTITY_FIELDS = frozenset({"formId", "formType", "sggVersion"})


@dataclass(frozen=True)
class RuntimeIdentity:
    """The target-specific values required to construct one Simpler ``Form``."""

    form_id: uuid.UUID
    form_type: str
    sgg_version: str


@functools.cache
def _records() -> dict[str, RuntimeIdentity]:
    document = json.loads(RUNTIME_IDENTITIES.read_text())
    if document.get("contract") != RUNTIME_IDENTITY_CONTRACT:
        raise ValueError("unsupported SGG form runtime identity contract")
    records = document.get("forms")
    if not isinstance(records, dict) or not records:
        raise ValueError("SGG form runtime identities have no forms")

    parsed: dict[str, RuntimeIdentity] = {}
    seen_uuids: set[uuid.UUID] = set()
    for portable_id, record in records.items():
        if not isinstance(portable_id, str) or not portable_id:
            raise ValueError("SGG form runtime identity has an invalid portable id")
        if not isinstance(record, dict) or set(record) != RUNTIME_IDENTITY_FIELDS:
            raise ValueError(
                f"SGG form runtime identity {portable_id!r} must contain exactly "
                f"{sorted(RUNTIME_IDENTITY_FIELDS)!r}"
            )
        form_id = _uuid(record, "formId", portable_id)
        if form_id in seen_uuids:
            raise ValueError(
                f"SGG form runtime identity {portable_id!r} reuses form UUID {form_id}"
            )
        seen_uuids.add(form_id)
        parsed[portable_id] = RuntimeIdentity(
            form_id=form_id,
            form_type=_nonempty(record, "formType", portable_id),
            sgg_version=_nonempty(record, "sggVersion", portable_id),
        )
    return parsed


def _nonempty(record: dict[str, Any], field: str, portable_id: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"SGG form runtime identity {portable_id!r} has invalid {field}")
    return value


def _uuid(record: dict[str, Any], field: str, portable_id: str) -> uuid.UUID:
    value = _nonempty(record, field, portable_id)
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"SGG form runtime identity {portable_id!r} has invalid {field}") from exc


def runtime_identity(portable_id: str) -> RuntimeIdentity:
    """Return one identity or fail with the portable id in the diagnostic."""

    try:
        return _records()[portable_id]
    except KeyError as exc:
        raise ValueError(f"no SGG runtime identity for portable form {portable_id!r}") from exc

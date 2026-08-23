"""Data-driven registration of portable forms in Simpler's legacy registry.

The SGG runtime-identity target owns form UUID, type, and schema version. This registration
file owns the smaller release opt-in set and instruction identifiers. Per-form Python modules
remain as compatibility import paths, but adding a portable form does not require one.
"""

from __future__ import annotations

import functools
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.form_spec.runtime_identity import runtime_identity

if TYPE_CHECKING:
    from src.db.models.competition_models import Form


REGISTRATIONS = Path(__file__).with_suffix(".json")
REGISTRATION_CONTRACT = "sgg-portable-form-registrations/v1"


@functools.cache
def _records() -> dict[str, dict[str, Any]]:
    document = json.loads(REGISTRATIONS.read_text())
    if document.get("contract") != REGISTRATION_CONTRACT:
        raise ValueError("unsupported portable form registration contract")
    records = document.get("forms")
    if not isinstance(records, dict) or not records:
        raise ValueError("portable form registration has no forms")
    for form_id, record in records.items():
        if not isinstance(record, dict):
            raise ValueError(f"portable form registration {form_id!r} is not an object")
        instruction_id = record.get("formInstructionId")
        if not isinstance(instruction_id, str):
            raise ValueError(f"portable form registration {form_id!r} has no instruction id")
        uuid.UUID(instruction_id)
    return records


def registration_metadata(form_id: str) -> tuple[uuid.UUID, str, uuid.UUID]:
    """Return legacy config identity from the target, manifest, and opt-in records."""
    record = _records()[form_id]
    manifest_path = ARTIFACTS / "forms" / form_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    meta = manifest["form"]
    return (
        runtime_identity(form_id).form_id,
        meta["shortFormName"],
        uuid.UUID(record["formInstructionId"]),
    )


@functools.cache
def portable_form(form_id: str) -> Form:
    """Build one opted-in portable form from producer and adapter declarations."""
    record = _records()[form_id]
    return build_runtime_form(
        form_id,
        form_instruction_id=uuid.UUID(record["formInstructionId"]),
    )


def registered_portable_forms() -> list[Form]:
    """Build every portable form explicitly opted into this SGG release."""
    return [portable_form(form_id) for form_id in _records()]

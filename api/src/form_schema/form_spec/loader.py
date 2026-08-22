"""Build a runtime `Form` from a form's emitted artifacts.

The artifacts are the contract. This loader reads JSON and applies the projection; it
does not know how the JSON was produced, and adding a second authoring path would not
touch it.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from src.form_schema.form_spec.bank import ARTIFACTS, _bank_projection, verify_artifacts
from src.form_schema.form_spec.projection import (
    Projection,
    project_rule_schema,
    project_schema,
    project_ui_schema,
)


class LoadedForm:
    """A form's projected artifacts, in the shapes `Form` columns expect."""

    def __init__(self, form_id: str, manifest: dict[str, Any], **artifacts: Any) -> None:
        self.form_id = form_id
        self.manifest = manifest
        self.form_json_schema: dict[str, Any] = artifacts["json_schema"]
        self.form_ui_schema: list[Any] = artifacts["ui_schema"]
        self.form_rule_schema: dict[str, Any] | None = artifacts["rule_schema"]

    @property
    def meta(self) -> dict[str, Any]:
        return self.manifest["form"]


#: Per-form legacy naming, kept outside `artifacts/` because that directory is rebuilt from
#: the emitted output and these files are the adapter's own.
PROJECTIONS = Path(__file__).parent / "projections"


def _projection_for(form_id: str) -> Projection:
    """The bank's projection, extended with this form's declared name exceptions."""
    bank = _bank_projection()
    overrides_path = PROJECTIONS / f"{form_id}.json"
    renames: dict[str, str] = {}
    annotations: dict[str, dict[str, Any]] = {}
    identifiers: dict[str, str] = {}
    if overrides_path.is_file():
        overrides = json.loads(overrides_path.read_text())
        declarations = overrides.get("renames", {})
        for source, declaration in declarations.items():
            if not isinstance(declaration, dict):
                raise ValueError(f"projection rename {source!r} must declare 'to' and 'why'")
            target = declaration.get("to")
            reason = declaration.get("why")
            if not isinstance(target, str) or not target:
                raise ValueError(f"projection rename {source!r} has no target")
            if not isinstance(reason, str) or not reason:
                raise ValueError(f"projection rename {source!r} has no reason")
            renames[source] = target
        for source, declaration in overrides.get("schemaAnnotations", {}).items():
            values = declaration.get("values") if isinstance(declaration, dict) else None
            reason = declaration.get("why") if isinstance(declaration, dict) else None
            if not isinstance(values, dict) or not values:
                raise ValueError(f"schema annotation {source!r} has no values")
            if not isinstance(reason, str) or not reason:
                raise ValueError(f"schema annotation {source!r} has no reason")
            annotations[source] = values
        for source, declaration in overrides.get("identifiers", {}).items():
            target = declaration.get("to") if isinstance(declaration, dict) else None
            reason = declaration.get("why") if isinstance(declaration, dict) else None
            if not isinstance(target, str) or not target:
                raise ValueError(f"identifier projection {source!r} has no target")
            if not isinstance(reason, str) or not reason:
                raise ValueError(f"identifier projection {source!r} has no reason")
            identifiers[source] = target
    return Projection(
        renames=renames,
        annotations=annotations,
        identifiers=identifiers,
        bank_uri=bank.bank_uri,
        block_ids=bank.block_ids,
        blocks=bank.blocks,
    )


def load_form(form_id: str, *, artifacts: Path | None = None) -> LoadedForm:
    if artifacts is None:
        verify_artifacts()
    root = (artifacts or ARTIFACTS) / "forms" / form_id
    manifest = json.loads((root / "manifest.json").read_text())
    canonical = json.loads((root / "schema.json").read_text())
    projection = _projection_for(form_id)

    rule_schema = json.loads((root / "sgg" / "rule-schema.json").read_text())
    ui_schema = json.loads((root / "sgg" / "ui-schema.json").read_text())
    # All three from the same projection, so a pointer and the property it addresses cannot
    # be spelled differently.
    return LoadedForm(
        form_id=form_id,
        manifest=manifest,
        json_schema=project_schema(canonical, projection),
        ui_schema=project_ui_schema(ui_schema, projection),
        rule_schema=project_rule_schema(rule_schema, projection) if rule_schema else rule_schema,
    )


def form_uuid(loaded: LoadedForm) -> uuid.UUID:
    return uuid.UUID(loaded.meta["formId"])

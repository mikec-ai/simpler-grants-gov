"""Build a runtime `Form` from a form's emitted artifacts.

The artifacts are the contract. This loader reads JSON and applies the projection; it
does not know how the JSON was produced, and adding a second authoring path would not
touch it.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.bank import ARTIFACTS, _bank_projection, verify_artifacts
from src.form_schema.form_spec.projection import (
    Projection,
    project_rule_schema,
    project_schema,
    project_ui_schema,
)
from src.form_schema.form_spec.xml_profile import project_grants_gov_xml_profile

if TYPE_CHECKING:
    from src.db.models.competition_models import Form


class LoadedForm:
    """A form's projected artifacts, in the shapes `Form` columns expect."""

    def __init__(self, form_id: str, manifest: dict[str, Any], **artifacts: Any) -> None:
        self.form_id = form_id
        self.manifest = manifest
        self.form_json_schema: dict[str, Any] = artifacts["json_schema"]
        self.form_ui_schema: list[Any] = artifacts["ui_schema"]
        self.form_rule_schema: dict[str, Any] | None = artifacts["rule_schema"]
        self.json_to_xml_schema: dict[str, Any] | None = artifacts.get("json_to_xml_schema")

    @property
    def meta(self) -> dict[str, Any]:
        return self.manifest["form"]


#: Per-form legacy naming, kept outside `artifacts/` because that directory is rebuilt from
#: the emitted output and these files are the adapter's own.
PROJECTIONS = Path(__file__).parent / "projections"


def _projection_for(form_id: str) -> Projection:
    """The bank's projection, extended with this form's declared name exceptions."""
    bank = _bank_projection()
    renames: dict[str, str] = {}
    annotations: dict[str, dict[str, Any]] = {}
    identifiers: dict[str, str] = {}

    def apply_overrides(profile_id: str, stack: tuple[str, ...] = ()) -> None:
        if profile_id in stack:
            chain = " -> ".join((*stack, profile_id))
            raise ValueError(f"projection inheritance cycle: {chain}")
        overrides_path = PROJECTIONS / f"{profile_id}.json"
        if not overrides_path.is_file():
            if stack:
                raise ValueError(f"projection profile {profile_id!r} does not exist")
            return
        overrides = json.loads(overrides_path.read_text())
        parent = overrides.get("extends")
        if parent is not None:
            if not isinstance(parent, str) or not parent:
                raise ValueError(f"projection profile {profile_id!r} has an invalid 'extends'")
            apply_overrides(parent, (*stack, profile_id))
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

    apply_overrides(form_id)
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
    xml_profile_path = root / "targets" / "grants-gov-xml.json"
    json_to_xml_schema = (
        project_grants_gov_xml_profile(json.loads(xml_profile_path.read_text()), projection)
        if xml_profile_path.is_file()
        else None
    )
    # All three from the same projection, so a pointer and the property it addresses cannot
    # be spelled differently.
    return LoadedForm(
        form_id=form_id,
        manifest=manifest,
        json_schema=project_schema(canonical, projection),
        ui_schema=project_ui_schema(ui_schema, projection),
        rule_schema=project_rule_schema(rule_schema, projection) if rule_schema else rule_schema,
        json_to_xml_schema=json_to_xml_schema,
    )


def form_uuid(loaded: LoadedForm) -> uuid.UUID:
    return uuid.UUID(loaded.meta["formId"])


def build_runtime_form(
    form_id: str,
    *,
    form_instruction_id: uuid.UUID | None = None,
) -> Form:
    """Build the ordinary Simpler runtime record from one portable form package.

    Form-specific semantics remain in the portable declaration. These arguments are only
    Simpler registry identity and capabilities that are not part of the portable contract.
    """

    # Local import avoids the existing registry -> question-bank -> adapter import cycle.
    from src.db.models.competition_models import Form

    loaded = load_form(form_id)
    meta = loaded.meta
    return Form(
        form_id=form_uuid(loaded),
        legacy_form_id=meta.get("legacyFormId"),
        form_name=meta["formName"],
        short_form_name=meta["shortFormName"],
        form_version=meta["formVersion"],
        agency_code=meta.get("agencyCode", "SGG"),
        omb_number=meta.get("ombNumber"),
        form_json_schema=loaded.form_json_schema,
        # The persisted model annotation predates the list-shaped UI contract used by
        # every registered form; keep the adapter's accurate type and cross that legacy
        # boundary explicitly.
        form_ui_schema=cast(Any, loaded.form_ui_schema),
        form_rule_schema=loaded.form_rule_schema,
        json_to_xml_schema=loaded.json_to_xml_schema,
        form_instruction_id=form_instruction_id,
        form_type=FormType(meta["formType"]),
        sgg_version=meta.get("sggVersion"),
        is_deprecated=False,
    )

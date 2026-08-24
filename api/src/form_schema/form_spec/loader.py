"""Build a runtime `Form` from a form's emitted artifacts.

The artifacts are the contract. This loader reads JSON and applies the projection; it
does not know how the JSON was produced, and adding a second authoring path would not
touch it.
"""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.bank import ARTIFACTS, _bank_projection, verify_artifacts
from src.form_schema.form_spec.operational_behavior import (
    ProjectedOperationalBehavior,
    project_operational_behavior,
)
from src.form_schema.form_spec.projection import (
    Projection,
    project_rule_schema,
    project_schema,
    project_ui_schema,
)
from src.form_schema.form_spec.response_normalization import (
    ResponseNormalizationPolicy,
    load_response_normalization,
    reject_rule_target_overlap,
)
from src.form_schema.form_spec.runtime_identity import runtime_identity
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
        self.response_normalization: ResponseNormalizationPolicy | None = artifacts.get(
            "response_normalization"
        )
        self.operational_behavior: tuple[ProjectedOperationalBehavior, ...] = artifacts.get(
            "operational_behavior", ()
        )

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


def _load_banked_form(
    form_id: str,
    *,
    artifacts: Path | None = None,
    project_xml: bool = True,
) -> LoadedForm:
    """Project one selected bank package without granting runtime eligibility.

    This is deliberately private. Production callers must use :func:`load_form`, whose
    runtime-identity check is the consumer-owned enablement boundary. The local/test
    preview registry uses this lower-level projector so banked packages can exercise the
    real renderer before receiving production identity or release approval.
    """

    if artifacts is None:
        verify_artifacts()
    root = (artifacts or ARTIFACTS) / "forms" / form_id
    if not root.is_dir():
        raise ValueError(f"portable form {form_id!r} is not selected in the artifact bank")
    manifest = json.loads((root / "manifest.json").read_text())
    canonical = json.loads((root / "schema.json").read_text())
    projection = _projection_for(form_id)

    rule_schema = json.loads((root / "sgg" / "rule-schema.json").read_text())
    ui_schema = json.loads((root / "sgg" / "ui-schema.json").read_text())
    xml_profile_path = root / "targets" / "grants-gov-xml.json"
    json_to_xml_schema = (
        project_grants_gov_xml_profile(json.loads(xml_profile_path.read_text()), projection)
        if project_xml and xml_profile_path.is_file()
        else None
    )
    projected_schema = project_schema(canonical, projection)
    projected_rule_schema = (
        project_rule_schema(rule_schema, projection) if rule_schema else rule_schema
    )
    response_normalization = load_response_normalization(
        root,
        manifest=manifest,
        projected_schema=projected_schema,
        projection=projection,
    )
    reject_rule_target_overlap(response_normalization, projected_rule_schema)
    evidence_path = root / "evidence.json"
    operational_behavior = (
        project_operational_behavior(
            json.loads(evidence_path.read_text()),
            form_id=form_id,
            target_projection=projection,
            projection_for=_projection_for,
            runtime_form_id_for=lambda source_form_id: runtime_identity(source_form_id).form_id,
        )
        if evidence_path.is_file()
        else ()
    )
    # All artifacts use the same projection, so a pointer and the property it addresses cannot
    # be spelled differently.
    return LoadedForm(
        form_id=form_id,
        manifest=manifest,
        json_schema=projected_schema,
        ui_schema=project_ui_schema(ui_schema, projection),
        rule_schema=projected_rule_schema,
        json_to_xml_schema=json_to_xml_schema,
        response_normalization=response_normalization,
        operational_behavior=operational_behavior,
    )


def load_form(form_id: str, *, artifacts: Path | None = None) -> LoadedForm:
    # Banking a producer package is deliberately broader than enabling it in Simpler.
    # A portable form may be present for provenance, review, and analysis without a
    # consumer-owned UUID, FormType, or compatibility projection.  The runtime loader
    # must fail before projecting such a form; enablement is the explicit identity
    # record, never the mere presence of vendored artifacts.
    runtime_identity(form_id)
    return _load_banked_form(form_id, artifacts=artifacts)


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
    from src.form_schema.jsonschema_resolver import resolve_jsonschema

    loaded = load_form(form_id)
    meta = loaded.meta
    identity = runtime_identity(form_id)
    return Form(
        form_id=identity.form_id,
        legacy_form_id=meta.get("legacyFormId"),
        form_name=meta["formName"],
        short_form_name=meta["shortFormName"],
        form_version=meta["formVersion"],
        agency_code=meta.get("agencyCode", "SGG"),
        omb_number=meta.get("ombNumber"),
        # Portable declarations retain $ref composition as their reviewable source of
        # truth. Simpler's current renderer expects an expanded schema, so resolving is
        # a generic consumer-adapter concern rather than a form-specific declaration.
        form_json_schema=resolve_jsonschema(copy.deepcopy(loaded.form_json_schema)),
        # The persisted model annotation predates the list-shaped UI contract used by
        # every registered form; keep the adapter's accurate type and cross that legacy
        # boundary explicitly.
        form_ui_schema=cast(Any, loaded.form_ui_schema),
        form_rule_schema=loaded.form_rule_schema,
        json_to_xml_schema=loaded.json_to_xml_schema,
        response_normalization=loaded.response_normalization,
        form_instruction_id=form_instruction_id,
        form_type=FormType(identity.form_type),
        sgg_version=identity.sgg_version,
        is_deprecated=False,
    )

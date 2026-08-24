"""Fail-closed local/test registration for every banked portable form.

Banking proves provenance and makes a package available for review; it does not grant a
production UUID or release it. This module creates a separate, deterministic preview
identity so the exact banked package can run through Simpler's ordinary registry, API,
and renderer in explicitly enabled lower environments.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from src.form_schema.form_spec.bank import ARTIFACT_MANIFEST
from src.form_schema.form_spec.loader import _load_banked_form

if TYPE_CHECKING:
    from src.db.models.competition_models import Form


PREVIEW_FLAG = "ENABLE_PORTABLE_FORM_PREVIEW"
BROWSER_FORM_IDS = "PORTABLE_BROWSER_FORM_IDS"
PREVIEW_ENVIRONMENTS = frozenset({"local", "test", "dev"})
PREVIEW_NAMESPACE = uuid.UUID("9370c7c0-c259-4f20-a1f3-e2fc595f75fd")


def portable_preview_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Require both a lower environment and an explicit opt-in flag."""

    values = environ if environ is not None else os.environ
    environment = values.get("ENVIRONMENT", "").strip().lower()
    enabled = values.get(PREVIEW_FLAG, "").strip().lower() in {"1", "true", "yes"}
    return environment in PREVIEW_ENVIRONMENTS and enabled


def banked_form_ids() -> tuple[str, ...]:
    """Return the producer-selected forms in their immutable manifest order."""

    document = json.loads(ARTIFACT_MANIFEST.read_text())
    forms = document.get("selection", {}).get("forms")
    if (
        not isinstance(forms, list)
        or not forms
        or any(not isinstance(form_id, str) or not form_id for form_id in forms)
        or len(forms) != len(set(forms))
    ):
        raise ValueError("portable artifact manifest has an invalid form selection")
    return tuple(forms)


def selected_browser_form_ids(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return the explicitly selected browser canaries, or the complete bank.

    Selection is intentionally lower-environment test configuration rather than form
    registration. It lets one form traverse the same real-runtime harness used by the full
    catalog without weakening the manifest boundary or adding a form-specific test path.
    """

    values = environ if environ is not None else os.environ
    available = banked_form_ids()
    raw = values.get(BROWSER_FORM_IDS, "").strip()
    if not raw:
        return available

    requested = tuple(value.strip() for value in raw.split(","))
    if any(not value for value in requested):
        raise ValueError(f"{BROWSER_FORM_IDS} must be a comma-separated list of non-empty form ids")
    if len(requested) != len(set(requested)):
        raise ValueError(f"{BROWSER_FORM_IDS} contains duplicate form ids")
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ValueError(
            f"{BROWSER_FORM_IDS} contains unknown form ids {unknown}; "
            f"available form ids are {list(available)}"
        )
    return requested


def preview_form_id(portable_id: str) -> uuid.UUID:
    """Return a stable UUID in a namespace reserved for non-production previews."""

    return uuid.uuid5(PREVIEW_NAMESPACE, portable_id)


def build_preview_form(portable_id: str) -> Form:
    """Build one banked package as a non-production Simpler ``Form``."""

    # Local import avoids the registry -> forms -> preview -> model import cycle.
    from src.db.models.competition_models import Form
    from src.form_schema.jsonschema_resolver import resolve_jsonschema

    # Preview is a renderer gate. XML projection remains behind its own exact-source and
    # lifecycle gates; several intentionally banked research forms still carry portable
    # XML shapes the current SGG serializer cannot execute. Do not prevent those forms
    # from reaching the renderer, and do not silently claim XML support here.
    loaded = _load_banked_form(portable_id, project_xml=False)
    meta = loaded.meta
    return Form(
        form_id=preview_form_id(portable_id),
        legacy_form_id=meta.get("legacyFormId"),
        form_name=f"[Portable preview] {meta['formName']}",
        short_form_name=f"portable-preview-{portable_id}",
        form_version=meta["formVersion"],
        agency_code=meta.get("agencyCode", "SGG"),
        omb_number=meta.get("ombNumber"),
        form_json_schema=resolve_jsonschema(copy.deepcopy(loaded.form_json_schema)),
        form_ui_schema=cast(Any, loaded.form_ui_schema),
        form_rule_schema=loaded.form_rule_schema,
        json_to_xml_schema=None,
        response_normalization=loaded.response_normalization,
        form_instruction_id=None,
        form_type=None,
        sgg_version=None,
        is_deprecated=False,
    )


def preview_portable_forms() -> list[Form]:
    """Build every selected portable package without a per-form registration list."""

    return [build_preview_form(form_id) for form_id in banked_form_ids()]

"""Build a capability-driven browser plan from the verified portable form bank.

The plan contains only mechanically observable facts from the selected, projected
artifacts.  It does not infer semantic test data and it never selects forms by name.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.form_schema.form_spec.bank import ARTIFACT_MANIFEST
from src.form_schema.form_spec.loader import _load_banked_form
from src.form_schema.form_spec.preview import (
    PREVIEW_FLAG,
    banked_form_ids,
    portable_preview_enabled,
    preview_form_id,
    selected_browser_form_ids,
)
from src.form_schema.jsonschema_resolver import resolve_jsonschema

PLAN_CONTRACT = "sgg-portable-browser-plan/v1"
SEED_OPPORTUNITY_ID = "6e3e3f80-f69c-5c5d-a5aa-5d4a117680d8"
SEED_COMPETITION_ID = "d3a39d43-7b96-54bf-b4c3-fde9849e13a2"
SEED_NAMESPACE = uuid.UUID("78315e9f-2aa5-4f9c-a130-b1f7fb44a19a")


def browser_seed_ids(form_ids: tuple[str, ...]) -> tuple[str, str]:
    """Return stable opportunity and competition IDs for one browser selection.

    The complete bank keeps its historical IDs. Bounded canaries receive identities
    derived solely from their ordered form selection, so they can coexist with full-bank
    and other canary seeds in the same local database.
    """

    if form_ids == banked_form_ids():
        return SEED_OPPORTUNITY_ID, SEED_COMPETITION_ID

    selection = ",".join(form_ids)
    return (
        str(uuid.uuid5(SEED_NAMESPACE, f"opportunity:{selection}")),
        str(uuid.uuid5(SEED_NAMESPACE, f"competition:{selection}")),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict]]:
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, (*path, str(index)))


def _schema_fields(
    schema: dict[str, Any],
    schema_path: str = "",
    response_path: str = "",
) -> Iterator[tuple[str, str, dict[str, Any], bool]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    required = schema.get("required", [])
    required_names = set(required) if isinstance(required, list) else set()
    for name, child in properties.items():
        if not isinstance(child, dict):
            continue
        child_schema_path = f"{schema_path}/properties/{name}"
        child_response_path = f"{response_path}/{name}"
        yield child_schema_path, child_response_path, child, name in required_names
        yield from _schema_fields(child, child_schema_path, child_response_path)
        items = child.get("items")
        if isinstance(items, dict):
            yield from _schema_fields(
                items,
                f"{child_schema_path}/items",
                f"{child_response_path}/*",
            )


def _rule_capabilities(rule_schema: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    attachments: list[dict] = []
    calculations: list[dict] = []
    for path, node in _walk(rule_schema):
        validation = node.get("gg_validation")
        if isinstance(validation, dict) and validation.get("rule") == "attachment":
            attachments.append({"rulePath": "/" + "/".join(path)})
        calculation = node.get("gg_pre_population")
        if isinstance(calculation, dict):
            calculations.append(
                {
                    "rulePath": "/" + "/".join(path),
                    "declaration": calculation,
                }
            )
    return attachments, calculations


def _resolve_schema_pointer(schema: dict[str, Any], pointer: str) -> dict[str, Any]:
    if not pointer.startswith("/"):
        raise ValueError(f"UI definition is not an absolute schema pointer: {pointer!r}")
    nodes: list[Any] = [schema]
    for encoded in pointer.removeprefix("/").split("/"):
        segment = encoded.replace("~1", "/").replace("~0", "~")
        nodes = [
            candidate
            for node in nodes
            if isinstance(node, dict)
            for candidate in _schema_keyword_values(node, segment)
        ]
        if not nodes:
            raise ValueError(f"UI definition does not resolve in projected schema: {pointer!r}")
    if not any(isinstance(node, dict) for node in nodes):
        raise ValueError(f"UI definition does not select a schema object: {pointer!r}")
    return next(node for node in nodes if isinstance(node, dict))


def _schema_keyword_values(schema: dict[str, Any], keyword: str) -> Iterator[Any]:
    if keyword in schema:
        yield schema[keyword]
    for branch in schema.get("allOf", []):
        if isinstance(branch, dict):
            yield from _schema_keyword_values(branch, keyword)


def _artifact_digests(manifest: dict[str, Any], form_id: str) -> dict[str, str]:
    prefix = f"dist/forms/{form_id}/"
    selected = {
        entry["path"][len(prefix) :]: entry["sha256"]
        for entry in manifest["files"]
        if isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and entry["path"].startswith(prefix)
    }
    required = ("manifest.json", "schema.json", "sgg/ui-schema.json", "sgg/rule-schema.json")
    missing = [path for path in required if path not in selected]
    if missing:
        raise ValueError(f"portable form {form_id!r} lacks artifact digests: {missing}")
    return {path: selected[path] for path in required}


def _capability(paths: list[dict], *, missing_reason: str) -> dict[str, Any]:
    return {
        "applicability": "applicable" if paths else "not_applicable",
        "declarations": paths,
        "reason": None if paths else missing_reason,
    }


def build_browser_plan() -> dict[str, Any]:
    """Return a deterministic plan whose form set is exactly the manifest selection."""

    if not portable_preview_enabled():
        raise ValueError(
            f"portable browser plans require ENVIRONMENT=local|test|dev and {PREVIEW_FLAG}=true"
        )

    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    form_ids = selected_browser_form_ids()
    seed_opportunity_id, seed_competition_id = browser_seed_ids(form_ids)
    forms: list[dict[str, Any]] = []

    for form_id in form_ids:
        loaded = _load_banked_form(form_id, project_xml=False)
        resolved_schema = resolve_jsonschema(loaded.form_json_schema)
        schema_fields = list(_schema_fields(resolved_schema))
        ui_nodes = list(_walk(loaded.form_ui_schema))
        ui_fields = [
            node
            for _, node in ui_nodes
            if node.get("type") in {"field", "fieldList"}
            and isinstance(node.get("definition"), str)
        ]
        for node in ui_fields:
            _resolve_schema_pointer(resolved_schema, node["definition"])

        repeaters = [
            {"definition": node["definition"], "name": node.get("name")}
            for node in ui_fields
            if node.get("type") == "fieldList"
        ]
        ui_attachments = [
            {"definition": node["definition"]}
            for node in ui_fields
            if node.get("widget") in {"Attachment", "MultipleAttachment"}
        ]
        conditionals = [
            {"definition": node["definition"], "conditional": node["conditional"]}
            for node in ui_fields
            if isinstance(node.get("conditional"), dict)
        ]
        readonly = [
            {"schemaPath": schema_path, "responsePath": response_path}
            for schema_path, response_path, node, _ in schema_fields
            if node.get("readOnly") is True
        ]
        readonly.extend(
            {"definition": node["definition"], "interaction": node["interaction"]}
            for node in ui_fields
            if node.get("interaction") in {"readOnly", "disabled"}
        )
        editable = [
            {"definition": node["definition"]}
            for node in ui_fields
            if node.get("type") == "field"
            and node.get("interaction") not in {"readOnly", "disabled"}
        ]
        required = [
            {"schemaPath": schema_path, "responsePath": response_path}
            for schema_path, response_path, _, is_required in schema_fields
            if is_required
        ]
        rule_attachments, calculations = _rule_capabilities(loaded.form_rule_schema or {})
        attachment_declarations = sorted(
            [*ui_attachments, *rule_attachments],
            key=lambda item: json.dumps(item, sort_keys=True),
        )

        forms.append(
            {
                "portableFormId": form_id,
                "previewFormId": str(preview_form_id(form_id)),
                "displayName": f"[Portable preview] {loaded.meta['formName']}",
                "form": loaded.meta,
                "artifactDigests": _artifact_digests(manifest, form_id),
                "counts": {
                    "uiNodes": len(ui_nodes),
                    "uiFields": len(ui_fields),
                    "schemaFields": len(schema_fields),
                },
                "stablePaths": {
                    "uiDefinitions": sorted(
                        {node["definition"] for node in ui_fields if "definition" in node}
                    ),
                    "schema": sorted(schema_path for schema_path, _, _, _ in schema_fields),
                },
                "stageA": [
                    "apply_render",
                    "initial_save_reload",
                    "print_render",
                    "accessibility",
                ],
                "capabilities": {
                    "editableScalar": _capability(
                        editable, missing_reason="no editable scalar is declared"
                    ),
                    "requiredField": _capability(
                        required, missing_reason="no required field is declared"
                    ),
                    "repeater": _capability(repeaters, missing_reason="no fieldList is declared"),
                    "attachment": _capability(
                        attachment_declarations,
                        missing_reason="no attachment widget or rule is declared",
                    ),
                    "conditional": _capability(
                        conditionals, missing_reason="no UI conditional is declared"
                    ),
                    "calculation": _capability(
                        calculations, missing_reason="no executable calculation is declared"
                    ),
                    "readOnly": _capability(
                        readonly, missing_reason="no protected field is declared"
                    ),
                },
            }
        )

    if tuple(form["portableFormId"] for form in forms) != form_ids:
        raise ValueError("browser plan form set diverged from the manifest selection")

    return {
        "contract": PLAN_CONTRACT,
        "manifestSha256": _sha256(ARTIFACT_MANIFEST),
        "source": manifest["source"],
        "consumerSeed": {
            "opportunityId": seed_opportunity_id,
            "competitionId": seed_competition_id,
        },
        "forms": forms,
    }


def write_browser_plan(path: Path) -> dict[str, Any]:
    plan = build_browser_plan()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return plan

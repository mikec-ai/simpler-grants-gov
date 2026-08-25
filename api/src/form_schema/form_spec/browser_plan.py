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


def _object_schemas(
    schema: dict[str, Any],
    schema_path: str = "",
    response_path: str = "",
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield object schemas reachable through the form's property tree.

    Definitions that are not referenced by the form are deliberately excluded. Array
    items use ``*`` in response paths so downstream browser probes can select a stable
    representative row without baking a form name into the harness.
    """

    yield schema_path, response_path, schema
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for name, child in properties.items():
        if not isinstance(child, dict):
            continue
        child_schema_path = f"{schema_path}/properties/{name}"
        child_response_path = f"{response_path}/{name}"
        yield from _object_schemas(child, child_schema_path, child_response_path)
        items = child.get("items")
        if isinstance(items, dict):
            yield from _object_schemas(
                items,
                f"{child_schema_path}/items",
                f"{child_response_path}/*",
            )


def _simple_schema_implications(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Project mechanically testable single-field ``if``/``then`` implications.

    This is capability discovery, not semantic inference: every path, pattern, title,
    and required relationship is copied from the resolved portable JSON Schema.
    """

    declarations: list[dict[str, Any]] = []
    for schema_path, response_path, node in _object_schemas(schema):
        properties = node.get("properties")
        branches = node.get("allOf")
        if not isinstance(properties, dict) or not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            condition = branch.get("if")
            consequence = branch.get("then")
            if not isinstance(condition, dict) or not isinstance(consequence, dict):
                continue
            condition_required = condition.get("required")
            consequence_required = consequence.get("required")
            if (
                not isinstance(condition_required, list)
                or len(condition_required) != 1
                or not isinstance(condition_required[0], str)
                or not isinstance(consequence_required, list)
                or len(consequence_required) != 1
                or not isinstance(consequence_required[0], str)
            ):
                continue
            trigger_name = condition_required[0]
            consequence_name = consequence_required[0]
            trigger_schema = properties.get(trigger_name)
            consequence_schema = properties.get(consequence_name)
            if not isinstance(trigger_schema, dict) or not isinstance(consequence_schema, dict):
                continue
            condition_properties = condition.get("properties", {})
            consequence_properties = consequence.get("properties", {})
            trigger_constraint = (
                condition_properties.get(trigger_name)
                if isinstance(condition_properties, dict)
                else None
            )
            consequence_constraint = (
                consequence_properties.get(consequence_name)
                if isinstance(consequence_properties, dict)
                else None
            )
            declarations.append(
                {
                    "objectSchemaPath": schema_path or "/",
                    "objectResponsePath": response_path or "/",
                    "trigger": {
                        "schemaPath": f"{schema_path}/properties/{trigger_name}",
                        "responsePath": f"{response_path}/{trigger_name}",
                        "title": trigger_schema.get("title"),
                        "constraint": trigger_constraint,
                    },
                    "consequence": {
                        "schemaPath": f"{schema_path}/properties/{consequence_name}",
                        "responsePath": f"{response_path}/{consequence_name}",
                        "title": consequence_schema.get("title"),
                        "required": True,
                        "constraint": consequence_constraint,
                    },
                }
            )
    return declarations


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


def _schema_pointer_nodes(schema: dict[str, Any], pointer: str) -> tuple[dict[str, Any], ...]:
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
    resolved = tuple(node for node in nodes if isinstance(node, dict))
    if not resolved:
        raise ValueError(f"UI definition does not select a schema object: {pointer!r}")
    return resolved


def _resolve_schema_pointer(schema: dict[str, Any], pointer: str) -> dict[str, Any]:
    return _schema_pointer_nodes(schema, pointer)[0]


def _schema_keyword_values(schema: dict[str, Any], keyword: str) -> Iterator[Any]:
    if keyword in schema:
        yield schema[keyword]
    for branch in schema.get("allOf", []):
        if isinstance(branch, dict):
            yield from _schema_keyword_values(branch, keyword)


def _ui_definition_paths(node: dict[str, Any]) -> tuple[str, ...]:
    """Return schema pointers exposed by one definition-backed UI node.

    Ordinary fields and repeaters address one schema pointer. Specialized
    ``multiField`` widgets address several pointers as one interaction surface.
    Normalize both declaration shapes here so capability discovery stays generic
    and downstream planning does not need to know a form or widget name.
    """

    definition = node.get("definition")
    if node.get("type") in {"field", "fieldList"} and isinstance(definition, str):
        return (definition,)
    if (
        node.get("type") == "multiField"
        and isinstance(definition, list)
        and definition
        and all(isinstance(path, str) for path in definition)
    ):
        return tuple(definition)
    return ()


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
        schema_implications = _simple_schema_implications(resolved_schema)
        ui_nodes = list(_walk(loaded.form_ui_schema))
        ui_fields = [node for _, node in ui_nodes if _ui_definition_paths(node)]
        static_content = [
            {
                "sectionName": node["name"],
                "label": node["label"],
                "paragraphs": [
                    paragraph for paragraph in node["description"].split("\n") if paragraph
                ],
                "sha256": hashlib.sha256(node["description"].encode()).hexdigest(),
            }
            for _, node in ui_nodes
            if node.get("type") == "section"
            and isinstance(node.get("name"), str)
            and isinstance(node.get("label"), str)
            and isinstance(node.get("description"), str)
            and node["description"]
        ]
        schema_nodes_by_definition: dict[str, tuple[dict[str, Any], ...]] = {}
        for node in ui_fields:
            for definition in _ui_definition_paths(node):
                schema_nodes_by_definition[definition] = _schema_pointer_nodes(
                    resolved_schema, definition
                )

        repeaters = [
            {"definition": node["definition"], "name": node.get("name")}
            for node in ui_fields
            if node.get("type") == "fieldList"
        ]
        attachment_widgets = {"Attachment", "AttachmentArray", "MultipleAttachment"}
        ui_attachments = [
            {"definition": node["definition"]}
            for node in ui_fields
            if node.get("widget") in attachment_widgets
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
        readonly_schema_paths = {
            schema_path
            for declaration in readonly
            if isinstance((schema_path := declaration.get("schemaPath")), str)
        }
        read_only_definitions = {
            definition
            for definition, candidates in schema_nodes_by_definition.items()
            if any(candidate.get("readOnly") is True for candidate in candidates)
        }
        readonly.extend(
            {"definition": definition}
            for definition in sorted(read_only_definitions - readonly_schema_paths)
        )
        readonly.extend(
            {"definition": node["definition"], "interaction": node["interaction"]}
            for node in ui_fields
            if node.get("interaction") in {"readOnly", "disabled"}
        )
        rule_attachments, calculations = _rule_capabilities(loaded.form_rule_schema or {})
        calculated_response_paths = {calculation["rulePath"] for calculation in calculations}
        response_path_by_schema_path = {
            schema_path: response_path for schema_path, response_path, _, _ in schema_fields
        }
        editable = [
            {"definition": definition}
            for node in ui_fields
            if node.get("type") in {"field", "multiField"}
            and node.get("interaction") not in {"readOnly", "disabled"}
            and node.get("widget") not in attachment_widgets
            for definition in _ui_definition_paths(node)
            if definition not in read_only_definitions
            if response_path_by_schema_path.get(definition) not in calculated_response_paths
        ]
        required = [
            {"schemaPath": schema_path, "responsePath": response_path}
            for schema_path, response_path, _, is_required in schema_fields
            if is_required
        ]
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
                        {
                            definition
                            for node in ui_fields
                            for definition in _ui_definition_paths(node)
                        }
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
                    "schemaImplication": _capability(
                        schema_implications,
                        missing_reason="no simple schema implication is declared",
                    ),
                    "calculation": _capability(
                        calculations, missing_reason="no executable calculation is declared"
                    ),
                    "readOnly": _capability(
                        readonly, missing_reason="no protected field is declared"
                    ),
                    "staticContent": _capability(
                        static_content,
                        missing_reason="no section-level static content is declared",
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

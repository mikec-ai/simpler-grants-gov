"""Uniform, evidence-bounded comparison of portable and existing Simpler forms."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.jsonschema_validator import _get_validator

CONTRACT = "sgg-portable-legacy-differential/v2"
COHORT_CONTRACT = "sgg-portable-legacy-cohort/v1"
COHORT_PATH = Path(__file__).with_name("differential-cohort.json")
FIELD_KEYWORDS = (
    "type",
    "format",
    "pattern",
    "enum",
    "const",
    "title",
    "description",
    "default",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "readOnly",
)


@dataclasses.dataclass(frozen=True)
class Difference:
    key: str
    portable: Any
    existing: Any


def _escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _deep_differences(portable: Any, existing: Any, pointer: str = "") -> list[Difference]:
    if isinstance(portable, dict) and isinstance(existing, dict):
        differences: list[Difference] = []
        for key in sorted(set(portable) | set(existing)):
            child = f"{pointer}/{_escape(key)}"
            if key not in portable:
                differences.append(Difference(child, None, existing[key]))
            elif key not in existing:
                differences.append(Difference(child, portable[key], None))
            else:
                differences.extend(_deep_differences(portable[key], existing[key], child))
        return differences
    if isinstance(portable, list) and isinstance(existing, list):
        differences = []
        for index in range(max(len(portable), len(existing))):
            child = f"{pointer}/{index}"
            if index >= len(portable):
                differences.append(Difference(child, None, existing[index]))
            elif index >= len(existing):
                differences.append(Difference(child, portable[index], None))
            else:
                differences.extend(_deep_differences(portable[index], existing[index], child))
        return differences
    return [] if portable == existing else [Difference(pointer or "/", portable, existing)]


def _composed(node: dict[str, Any]) -> dict[str, Any]:
    branches = [
        branch
        for branch in node.get("allOf", [])
        if isinstance(branch, dict) and "if" not in branch
    ]
    if not branches:
        return node
    merged: dict[str, Any] = {}
    for source in (*branches, node):
        collapsed = _composed(source) if source is not node else source
        for key, value in collapsed.items():
            if key == "allOf":
                continue
            if key == "properties":
                merged.setdefault("properties", {}).update(value)
            elif key == "required":
                merged["required"] = [*merged.get("required", []), *value]
            else:
                merged[key] = value
    return merged


def _ui_pointers(ui_schema: Any) -> list[str]:
    pointers: list[str] = []
    if isinstance(ui_schema, list):
        for item in ui_schema:
            pointers.extend(_ui_pointers(item))
    elif isinstance(ui_schema, dict):
        definition = ui_schema.get("definition")
        candidates = definition if isinstance(definition, list) else [definition]
        pointers.extend(value for value in candidates if isinstance(value, str))
        pointers.extend(_ui_pointers(ui_schema.get("children", [])))
    return pointers


def _rendered_field(schema: dict[str, Any], pointer: str) -> tuple[dict[str, Any], bool] | None:
    node = _composed(schema)
    parent: dict[str, Any] = {}
    leaf = ""
    steps = [step for step in pointer.strip("/").split("/") if step]
    index = 0
    while index < len(steps):
        step = steps[index]
        if step == "properties":
            index += 1
            if index >= len(steps):
                return None
            leaf = steps[index]
            parent = node
            child = (node.get("properties") or {}).get(leaf)
            if not isinstance(child, dict):
                return None
            node = _composed(child)
        elif step == "items":
            items = node.get("items")
            if not isinstance(items, dict):
                return None
            parent, leaf = {}, ""
            node = _composed(items)
        else:
            return None
        index += 1
    return node, leaf in (parent.get("required") or [])


def _schema_differences(
    portable: dict[str, Any], existing: dict[str, Any], portable_ui: Any, existing_ui: Any
) -> list[Difference]:
    differences: list[Difference] = []
    pointers = dict.fromkeys([*_ui_pointers(existing_ui), *_ui_pointers(portable_ui)])
    for pointer in pointers:
        ours = _rendered_field(portable, pointer)
        theirs = _rendered_field(existing, pointer)
        if ours is None or theirs is None:
            differences.append(
                Difference(f"{pointer}#reachable", ours is not None, theirs is not None)
            )
            continue
        ours_schema, ours_required = ours
        theirs_schema, theirs_required = theirs
        if ours_required != theirs_required:
            differences.append(Difference(f"{pointer}#required", ours_required, theirs_required))
        for keyword in FIELD_KEYWORDS:
            if ours_schema.get(keyword) != theirs_schema.get(keyword):
                differences.append(
                    Difference(
                        f"{pointer}#{keyword}",
                        ours_schema.get(keyword),
                        theirs_schema.get(keyword),
                    )
                )
    portable_conditions = sorted(
        json.dumps(branch, sort_keys=True)
        for branch in portable.get("allOf", [])
        if isinstance(branch, dict) and "if" in branch
    )
    existing_conditions = sorted(
        json.dumps(branch, sort_keys=True)
        for branch in existing.get("allOf", [])
        if isinstance(branch, dict) and "if" in branch
    )
    if portable_conditions != existing_conditions:
        differences.append(
            Difference("/#conditionalBranches", portable_conditions, existing_conditions)
        )
    return differences


def _example(node: dict[str, Any]) -> Any:
    node = _composed(node)
    if "const" in node:
        return copy.deepcopy(node["const"])
    values = node.get("enum")
    if isinstance(values, list) and values:
        return copy.deepcopy(values[0])
    node_type = node.get("type")
    if node_type == "object" or isinstance(node.get("properties"), dict):
        return {name: _example(child) for name, child in node.get("properties", {}).items()}
    if node_type == "array" or isinstance(node.get("items"), dict):
        return [_example(node.get("items", {}))]
    if node_type == "boolean":
        return False
    if node_type in {"integer", "number"}:
        return node.get("minimum", 0)
    if node.get("format") == "date":
        return "2026-01-01"
    if node.get("format") == "email":
        return "example@example.com"
    if node.get("format") in {"uri", "uri-reference"}:
        return "https://example.com"
    pattern = node.get("pattern", "")
    if "uuid" in node.get("format", "").lower() or "[0-9a-fA-F]{8}" in pattern:
        return "00000000-0000-4000-8000-000000000000"
    minimum_length = max(1, int(node.get("minLength", 1)))
    return "x" * minimum_length


def _leaf_paths(schema: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    node = _composed(schema)
    if isinstance(node.get("properties"), dict):
        return [
            path
            for name, child in node["properties"].items()
            for path in _leaf_paths(child, (*prefix, name))
        ]
    if isinstance(node.get("items"), dict):
        return _leaf_paths(node["items"], (*prefix, "[]"))
    return [prefix] if prefix else []


def _mutations(schema: dict[str, Any]) -> Iterable[dict[str, Any]]:
    seed = _example(schema)
    if not isinstance(seed, dict):
        return
    yield {}
    yield seed
    for path in _leaf_paths(schema):
        for replacement in (None, "", "x" * 200, 17, "not-a-listed-value"):
            payload = copy.deepcopy(seed)
            node: Any = payload
            for step in path[:-1]:
                node = node[0] if step == "[]" else node.get(step)
                if node is None:
                    break
            else:
                leaf = path[-1]
                if leaf != "[]":
                    if replacement is None:
                        node.pop(leaf, None)
                    else:
                        node[leaf] = replacement
                    yield payload


def _verdicts(validator: Any, payload: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (issue.json_path, str(issue.validator), issue.message)
        for issue in validator.iter_errors(payload)
    }


def _validation_differences(
    portable: dict[str, Any], existing: dict[str, Any]
) -> tuple[int, list[Difference]]:
    differences: list[Difference] = []
    payloads = list(_mutations(existing))
    portable_validator = _get_validator(portable)
    existing_validator = _get_validator(existing)
    for index, payload in enumerate(payloads):
        ours = _verdicts(portable_validator, payload)
        theirs = _verdicts(existing_validator, payload)
        for issue in sorted(ours ^ theirs):
            side = "portable" if issue in ours else "existing"
            field, issue_type, message = issue
            key = f"{field.removeprefix('$.')}#{issue_type}"
            differences.append(
                Difference(
                    key,
                    {"payload": index, "message": message} if side == "portable" else None,
                    {"payload": index, "message": message} if side == "existing" else None,
                )
            )
    return len(payloads), differences


def _dimension(
    differences: list[Difference], allowed: dict[str, dict[str, str]], **evidence: Any
) -> dict[str, Any]:
    grouped: dict[str, list[Difference]] = {}
    for difference in differences:
        grouped.setdefault(difference.key, []).append(difference)
    observed = set(grouped)
    expected = set(allowed)
    unexpected = sorted(observed - expected)
    stale = sorted(expected - observed)
    status = "failed" if unexpected or stale else "intentional_delta" if differences else "parity"
    return {
        "status": status,
        "differenceKeyCount": len(grouped),
        "observationCount": len(differences),
        "intentionalDeltas": [
            {"key": key, "observations": len(grouped[key]), **allowed[key]}
            for key in sorted(observed & expected)
        ],
        "unexpected": [
            {
                **dataclasses.asdict(grouped[key][0]),
                "observations": len(grouped[key]),
            }
            for key in unexpected
        ],
        "staleAllowances": stale,
        **evidence,
    }


def _allowed_deltas(record: dict[str, Any], dimension: str) -> dict[str, dict[str, str]]:
    groups = record.get("intentionalDeltas", {}).get(dimension, [])
    allowed: dict[str, dict[str, str]] = {}
    for group in groups:
        declaration = {"reason": group["reason"], "evidence": group["evidence"]}
        for key in group["keys"]:
            if key in allowed:
                raise ValueError(
                    f"{record.get('portableFormId')}.{dimension} repeats delta key {key!r}"
                )
            allowed[key] = declaration
    return allowed


def _load_cohort(path: Path) -> dict[str, Any]:
    cohort = json.loads(path.read_text())
    if cohort.get("contract") != COHORT_CONTRACT:
        raise ValueError(f"unsupported differential cohort contract: {cohort.get('contract')!r}")
    forms = cohort.get("forms")
    if not isinstance(forms, list) or len(forms) < 7:
        raise ValueError("differential cohort must declare at least seven forms")
    form_ids = [form.get("portableFormId") for form in forms if isinstance(form, dict)]
    if len(form_ids) != len(forms) or any(not isinstance(form_id, str) for form_id in form_ids):
        raise ValueError("every differential cohort form must have a portableFormId")
    if len(form_ids) != len(set(form_ids)):
        raise ValueError("differential cohort contains duplicate portable form ids")
    api_root = Path(__file__).resolve().parents[3]
    for form in forms:
        for dimension in ("schema", "ui", "validation", "rules"):
            groups = form.get("intentionalDeltas", {}).get(dimension, [])
            if not isinstance(groups, list):
                raise ValueError(
                    f"{form.get('portableFormId')}.{dimension} deltas must be an array"
                )
            for group in groups:
                keys = group.get("keys") if isinstance(group, dict) else None
                if (
                    not isinstance(keys, list)
                    or not keys
                    or any(not isinstance(key, str) or not key for key in keys)
                    or not group.get("reason")
                    or not group.get("evidence")
                ):
                    raise ValueError(
                        f"{form.get('portableFormId')}.{dimension} delta lacks keys, reason, or evidence"
                    )
                if not (api_root / group["evidence"]).is_file():
                    raise ValueError(
                        f"{form.get('portableFormId')}.{dimension} evidence does not exist: "
                        f"{group['evidence']}"
                    )
            _allowed_deltas(form, dimension)
    return cohort


def _consumer_revision() -> str:
    root = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=False, capture_output=True, text=True
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        detail = result.stderr.strip() or "Git did not return a full revision"
        raise ValueError(f"unable to resolve consumer revision: {detail}")
    return revision


def _validated_revision(revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("consumer revision must be a full lowercase 40-character Git SHA")
    return revision


def compare_cohort(
    cohort_path: Path = COHORT_PATH, *, consumer_revision: str | None = None
) -> list[dict[str, Any]]:
    """Compare every declaratively selected form through the same mechanism."""
    cohort = _load_cohort(cohort_path)
    revision = _validated_revision(
        consumer_revision if consumer_revision is not None else _consumer_revision()
    )
    source = {
        "repository": "https://github.com/mikec-ai/simpler-grants-gov",
        "revision": revision,
        "cohortSha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
    }
    receipts: list[dict[str, Any]] = []
    forms_root = Path(forms_package.__file__).parent
    for record in cohort["forms"]:
        portable_id = record["portableFormId"]
        existing = load_versioned_form(
            forms_root / record["existingDirectory"], record["existingVersion"]
        )
        portable = load_form(portable_id)
        portable_schema = resolve_jsonschema(copy.deepcopy(portable.form_json_schema))
        existing_schema = resolve_jsonschema(copy.deepcopy(existing.FORM_JSON_SCHEMA))
        allowed = {
            dimension: _allowed_deltas(record, dimension)
            for dimension in ("schema", "ui", "validation", "rules")
        }
        schema = _dimension(
            _schema_differences(
                portable_schema,
                existing_schema,
                portable.form_ui_schema,
                existing.FORM_UI_SCHEMA,
            ),
            allowed["schema"],
        )
        ui = _dimension(
            _deep_differences(portable.form_ui_schema, existing.FORM_UI_SCHEMA),
            allowed["ui"],
        )
        case_count, validation_differences = _validation_differences(
            portable_schema, existing_schema
        )
        validation = _dimension(validation_differences, allowed["validation"], caseCount=case_count)
        portable_rules = portable.form_rule_schema
        existing_rules = getattr(existing, "FORM_RULE_SCHEMA", None)
        if portable_rules is None and existing_rules is None:
            rules = {
                "status": "not_applicable",
                "reason": "neither implementation declares a rule schema",
            }
        else:
            rules = _dimension(
                _deep_differences(portable_rules, existing_rules),
                allowed["rules"],
                comparison="declaration",
            )
        dimensions = {"schema": schema, "ui": ui, "validation": validation, "rules": rules}
        receipts.append(
            {
                "contract": CONTRACT,
                "source": source,
                "portableFormId": portable_id,
                "existingOracle": {
                    "directory": record["existingDirectory"],
                    "version": record["existingVersion"],
                },
                "dimensions": dimensions,
                "unsupportedDimensions": {
                    "xml": {
                        "status": "unavailable",
                        "reason": "the initial static differential does not compare serialized XML",
                    },
                    "ruleOutcomes": {
                        "status": "unavailable",
                        "reason": "rules are compared as declarations; a generic outcome corpus is not yet available",
                    },
                    "runtimeLifecycle": {
                        "status": "unavailable",
                        "reason": "runtime behavior is reported by the separate generic browser receipt",
                    },
                },
                "comparisonGate": all(
                    dimension["status"] in {"parity", "intentional_delta", "not_applicable"}
                    for dimension in dimensions.values()
                ),
            }
        )
    return receipts

"""Generic compatibility normalization for portable form responses.

The portable package owns exact response paths and reviewed evidence. This adapter only
validates, projects, and executes the closed contract; it contains no form identities or
field-name inference.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.form_schema.form_spec.projection import Projection, project_response_pointer

CONTRACT = "grants-form-response-normalization/v1"
OPERATION = "empty-string-to-absent"
_POINTER_ESCAPE = re.compile(r"~(?:0|1)")
_AMBIGUOUS_COMPOSITION_KEYS = {"anyOf", "oneOf", "not", "if", "then", "else"}
_RULE_SCHEMA_CONTROL_KEYS = {
    "gg_pre_population",
    "gg_post_population",
    "gg_validation",
    "gg_type",
}


@dataclass(frozen=True)
class ResponseNormalizationOperation:
    path: str
    operation: str
    evidence_ref: str


@dataclass(frozen=True)
class ResponseNormalizationPolicy:
    contract: str
    operations: tuple[ResponseNormalizationOperation, ...]


def _exact_keys(value: Any, expected: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{context} must contain exactly {sorted(expected)}")
    return value


def _decode_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise ValueError(f"invalid response normalization path {path!r}")
    tokens = path[1:].split("/")
    for token in tokens:
        if token == "":
            raise ValueError(f"invalid empty JSON Pointer token in {path!r}")
        if re.search(r"~(?![01])", token):
            raise ValueError(f"invalid JSON Pointer escape in {path!r}")
    return [
        _POINTER_ESCAPE.sub(lambda match: "/" if match.group() == "~1" else "~", token)
        for token in tokens
    ]


def _schema_layers(schema: dict[str, Any]) -> list[dict[str, Any]]:
    layers = [schema]
    for extension in schema.get("allOf", []):
        if not isinstance(extension, dict):
            raise ValueError("response normalization target crosses an invalid allOf schema")
        layers.extend(_schema_layers(extension))
    return layers


def _reject_ambiguous_composition(states: list[dict[str, Any]], path: str) -> None:
    if any(_AMBIGUOUS_COMPOSITION_KEYS.intersection(layer) for layer in states):
        raise ValueError(
            f"response normalization path {path} uses unsupported conditional or "
            "alternative schema composition"
        )


def _validate_target(schema: dict[str, Any], path: str) -> None:
    states = _schema_layers(schema)
    tokens = _decode_pointer(path)
    for index, token in enumerate(tokens):
        _reject_ambiguous_composition(states, path)
        if any(layer.get("type") == "array" or "items" in layer for layer in states):
            raise ValueError(f"response normalization path {path} traverses an array")
        if index == len(tokens) - 1 and any(token in layer.get("required", []) for layer in states):
            raise ValueError(f"response normalization path {path} targets a required property")
        properties = [
            layer["properties"][token]
            for layer in states
            if isinstance(layer.get("properties"), dict) and token in layer["properties"]
        ]
        if not properties or any(not isinstance(value, dict) for value in properties):
            raise ValueError(f"response normalization path {path} does not resolve exactly")
        states = [child for value in properties for child in _schema_layers(value)]

    _reject_ambiguous_composition(states, path)
    if any(layer.get("type") == "array" or "items" in layer for layer in states):
        raise ValueError(f"response normalization path {path} targets an array")
    types = [
        item
        for layer in states
        for item in (
            layer.get("type", [])
            if isinstance(layer.get("type"), list)
            else [layer["type"]] if "type" in layer else []
        )
    ]
    if "string" not in types or any(item != "string" for item in types):
        raise ValueError(f"response normalization path {path} must target a non-null string")
    minima = [layer["minLength"] for layer in states if isinstance(layer.get("minLength"), int)]
    if not minima or max(minima) < 1:
        raise ValueError(f"response normalization path {path} must reject a present empty string")


def load_response_normalization(
    root: Path,
    *,
    manifest: dict[str, Any],
    projected_schema: dict[str, Any],
    projection: Projection,
) -> ResponseNormalizationPolicy | None:
    """Load, verify, and project an optional normalization artifact."""
    artifact = manifest.get("artifacts", {}).get("response-normalization.json")
    path = root / "response-normalization.json"
    if artifact is None:
        if path.exists():
            raise ValueError("undeclared response-normalization.json artifact")
        return None
    declaration = _exact_keys(artifact, {"origin", "sha256"}, "normalization manifest entry")
    if declaration["origin"] != "passthrough" or not isinstance(declaration["sha256"], str):
        raise ValueError("response normalization must be a hashed passthrough artifact")
    if not path.is_file():
        raise ValueError("declared response-normalization.json artifact is missing")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != declaration["sha256"]:
        raise ValueError("response normalization digest does not match its manifest")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("response normalization is not valid JSON") from exc
    document = _exact_keys(document, {"contract", "form", "operations"}, "normalization")
    if document["contract"] != CONTRACT:
        raise ValueError(f"unsupported response normalization contract {document['contract']!r}")
    form = _exact_keys(document["form"], {"id", "formVersion"}, "normalization form")
    if form != {
        "id": manifest.get("form", {}).get("id"),
        "formVersion": manifest.get("form", {}).get("formVersion"),
    }:
        raise ValueError("response normalization form identity does not match its manifest")
    if not isinstance(document["operations"], list) or not document["operations"]:
        raise ValueError("response normalization operations must be a non-empty array")

    evidence_path = root / "evidence.json"
    if not evidence_path.is_file():
        raise ValueError("response normalization requires packaged evidence")
    evidence = json.loads(evidence_path.read_bytes())
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for record in evidence.get("responseNormalizationEvidence", []):
        record_id = record.get("id") if isinstance(record, dict) else None
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("response normalization evidence has an invalid id")
        if record_id in evidence_by_id:
            raise ValueError(f"duplicate response normalization evidence id {record_id}")
        evidence_by_id[record_id] = record
    sources_by_id: dict[str, dict[str, Any]] = {}
    for source in evidence.get("sources", []):
        source_id = source.get("id") if isinstance(source, dict) else None
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("response normalization evidence source has an invalid id")
        if source_id in sources_by_id:
            raise ValueError(f"duplicate response normalization evidence source id {source_id}")
        sources_by_id[source_id] = source

    # Local import avoids the existing resolver -> question bank -> form-spec package cycle.
    from src.form_schema.jsonschema_resolver import resolve_jsonschema

    resolved_schema = resolve_jsonschema(copy.deepcopy(projected_schema))
    operations: list[ResponseNormalizationOperation] = []
    seen: set[str] = set()
    for index, raw_operation in enumerate(document["operations"]):
        operation = _exact_keys(
            raw_operation, {"path", "operation", "evidenceRef"}, f"normalization operation {index}"
        )
        canonical_path = operation["path"]
        _decode_pointer(canonical_path)
        if canonical_path in seen:
            raise ValueError(f"duplicate response normalization path {canonical_path}")
        seen.add(canonical_path)
        if operation["operation"] != OPERATION:
            raise ValueError(
                f"unsupported response normalization operation {operation['operation']!r}"
            )
        evidence_ref = operation["evidenceRef"]
        if not isinstance(evidence_ref, str) or not evidence_ref:
            raise ValueError("response normalization evidenceRef must be a non-empty string")
        record = evidence_by_id.get(evidence_ref)
        if not isinstance(record, dict):
            raise ValueError(f"unresolved response normalization evidenceRef {evidence_ref}")
        if (
            record.get("reviewStatus") != "reviewed"
            or record.get("canonicalPath") != canonical_path
            or record.get("operation") != OPERATION
            or record.get("authority") != "official_source"
        ):
            raise ValueError(
                f"response normalization evidenceRef {evidence_ref} "
                "does not exactly review the operation"
            )
        citations = record.get("sourceEvidence")
        if not isinstance(citations, list) or not citations:
            raise ValueError(
                f"response normalization evidenceRef {evidence_ref} has no source evidence"
            )
        for citation in citations:
            source_id = citation.get("sourceId") if isinstance(citation, dict) else None
            if not isinstance(source_id, str) or not source_id:
                raise ValueError(
                    f"response normalization evidenceRef {evidence_ref} has an invalid source id"
                )
            source = sources_by_id.get(source_id)
            if not isinstance(source, dict):
                raise ValueError(
                    f"response normalization evidenceRef {evidence_ref} names missing source {source_id}"
                )
            if source.get("type") == "implementation":
                raise ValueError(
                    f"response normalization evidenceRef {evidence_ref} "
                    "uses implementation evidence as official source"
                )
        projected_path = project_response_pointer(canonical_path, projection)
        _validate_target(resolved_schema, projected_path)
        operations.append(ResponseNormalizationOperation(projected_path, OPERATION, evidence_ref))
    return ResponseNormalizationPolicy(CONTRACT, tuple(operations))


def reject_rule_target_overlap(
    policy: ResponseNormalizationPolicy | None,
    rule_schema: dict[str, Any] | None,
) -> None:
    """Reject a form whose rules can mutate a normalization target.

    Rule population handlers own their target path and may remove it when they produce
    ``None``. Keeping those targets disjoint from capture-only normalization makes it safe
    to restore exact raw blanks after rule processing without guessing rule intent.
    """
    if policy is None or rule_schema is None:
        return

    mutation_targets: set[str] = set()

    def walk(node: dict[str, Any], path: tuple[str, ...]) -> None:
        if "gg_pre_population" in node or "gg_post_population" in node:
            encoded = "/".join(token.replace("~", "~0").replace("/", "~1") for token in path)
            if encoded:
                mutation_targets.add(f"/{encoded}")
        for key, value in node.items():
            if key not in _RULE_SCHEMA_CONTROL_KEYS and isinstance(value, dict):
                walk(value, (*path, key))

    walk(rule_schema, ())
    for operation in policy.operations:
        if operation.path in mutation_targets:
            raise ValueError(
                f"response normalization path {operation.path} overlaps a rule mutation target"
            )


def _lookup_parent(response: dict[str, Any], path: str) -> tuple[dict[str, Any] | None, str]:
    tokens = _decode_pointer(path)
    current: Any = response
    for token in tokens[:-1]:
        if not isinstance(current, dict):
            raise ValueError(f"response shape is incompatible with normalization path {path}")
        if token not in current:
            return None, tokens[-1]
        current = current[token]
    if not isinstance(current, dict):
        raise ValueError(f"response shape is incompatible with normalization path {path}")
    return current, tokens[-1]


def normalize_response(
    response: dict[str, Any], policy: ResponseNormalizationPolicy | None
) -> dict[str, Any]:
    """Return a normalized copy; never mutate the captured response."""
    normalized = copy.deepcopy(response)
    if policy is None:
        return normalized
    for operation in policy.operations:
        parent, leaf = _lookup_parent(normalized, operation.path)
        if parent is not None and parent.get(leaf) == "":
            del parent[leaf]
    return normalized


def merge_rule_response(
    raw_response: dict[str, Any],
    rule_response: dict[str, Any],
    policy: ResponseNormalizationPolicy | None,
) -> dict[str, Any]:
    """Persist rule writes while retaining capture-only exact empty strings."""
    merged = copy.deepcopy(rule_response)
    if policy is None:
        return merged
    for operation in policy.operations:
        raw_parent, leaf = _lookup_parent(raw_response, operation.path)
        if raw_parent is None or raw_parent.get(leaf) != "":
            continue
        merged_parent, _ = _lookup_parent(merged, operation.path)
        if merged_parent is not None and leaf not in merged_parent:
            merged_parent[leaf] = ""
    return merged

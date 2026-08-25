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

import jsonschema

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.bank import ARTIFACT_MANIFEST, ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.jsonschema_validator import _get_validator

CONTRACT = "sgg-portable-legacy-differential/v3"
DISPOSITION_CONTRACT = "sgg-portable-legacy-differential-disposition/v1"
COHORT_CONTRACT = "sgg-portable-legacy-cohort/v1"
COHORT_PATH = Path(__file__).with_name("differential-cohort.json")
LEDGER_CONTRACT = "grants-form-parity-delta-ledger/v1"
LEDGER_SOURCE_PATH = "parity/legacy-deltas.v1.json"
LEDGER_PATH = ARTIFACTS / "governance" / LEDGER_SOURCE_PATH
LEDGER_SCHEMA_SOURCE_PATH = "contract/v1/parity-delta-ledger.schema.json"
LEDGER_SCHEMA_PATH = ARTIFACTS / "governance" / LEDGER_SCHEMA_SOURCE_PATH
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
    differences: list[Difference], declared: dict[str, dict[str, Any]], **evidence: Any
) -> dict[str, Any]:
    grouped: dict[str, list[Difference]] = {}
    for difference in differences:
        grouped.setdefault(difference.key, []).append(difference)
    observed = set(grouped)
    expected = set(declared)
    unexpected = sorted(observed - expected)
    stale = sorted(expected - observed)
    matched = [declared[key] for key in sorted(observed & expected)]
    if unexpected or stale or any(row["review"]["status"] == "rejected" for row in matched):
        status = "failed"
    elif any(row["classification"] == "unresolved_mismatch" for row in matched):
        status = "unresolved"
    elif any(row["review"]["status"] == "proposed" for row in matched):
        status = "proposed_delta"
    elif differences:
        status = "reviewed_delta"
    else:
        status = "parity"
    return {
        "status": status,
        "differenceKeyCount": len(grouped),
        "observationCount": len(differences),
        "deltas": [
            {"key": key, "observations": len(grouped[key]), **declared[key]}
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
    return cohort


def _load_delta_ledger(
    path: Path = LEDGER_PATH,
    *,
    manifest_path: Path = ARTIFACT_MANIFEST,
    schema_path: Path = LEDGER_SCHEMA_PATH,
    receipt_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selection = json.loads(manifest_path.read_text())
    pinned = {row.get("path"): row for row in selection.get("files", [])}

    def verified_payload(source_path: str, local_path: Path) -> tuple[bytes, dict[str, Any]]:
        source_record = pinned.get(source_path)
        if source_record is None:
            raise ValueError(f"portable artifact selection does not pin {source_path}")
        payload = local_path.read_bytes()
        if len(payload) != source_record.get("size") or hashlib.sha256(
            payload
        ).hexdigest() != source_record.get("sha256"):
            raise ValueError(f"{source_path} does not match its pinned producer artifact")
        return payload, source_record

    payload, source_record = verified_payload(LEDGER_SOURCE_PATH, path)
    schema_payload, schema_record = verified_payload(LEDGER_SCHEMA_SOURCE_PATH, schema_path)
    ledger = json.loads(payload)
    schema = json.loads(schema_payload)
    errors = sorted(
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
        ).iter_errors(ledger),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/" + "/".join(str(step) for step in first.absolute_path)
        raise ValueError(f"parity delta ledger contract failed at {location}: {first.message}")
    if ledger.get("contract") != LEDGER_CONTRACT:
        raise ValueError(f"unsupported parity delta ledger: {ledger.get('contract')!r}")
    verification = ledger["evidenceVerification"]
    receipt_source_path = verification["receipt"]
    resolved_receipt_path = receipt_path or ARTIFACTS / "governance" / receipt_source_path
    receipt_payload, receipt_record = verified_payload(receipt_source_path, resolved_receipt_path)
    receipt = json.loads(receipt_payload)
    if receipt.get("contract") != "grants-form-parity-evidence-verification/v1":
        raise ValueError("unsupported parity delta evidence verification receipt")
    if any(receipt.get(field) != verification.get(field) for field in ("repository", "revision")):
        raise ValueError("parity delta evidence verification receipt does not match the ledger pin")
    receipt_files = receipt.get("files")
    if not isinstance(receipt_files, list):
        raise ValueError("parity delta evidence verification receipt has no files")
    verified_paths: dict[str, str] = {}
    for entry in receipt_files:
        evidence_path = entry.get("path") if isinstance(entry, dict) else None
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if (
            not isinstance(evidence_path, str)
            or not evidence_path
            or evidence_path in verified_paths
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("parity delta evidence verification receipt has invalid files")
        verified_paths[evidence_path] = digest
    records = ledger.get("records")
    if not isinstance(records, list):
        raise ValueError("parity delta ledger records must be an array")
    exact_targets: set[tuple[str, str, str]] = set()
    ids: set[str] = set()
    used_verified_paths: set[str] = set()
    for record in records:
        target = record.get("target", {}) if isinstance(record, dict) else {}
        form_id = record.get("formId")
        dimension = target.get("dimension")
        difference_key = target.get("differenceKey")
        candidate = (form_id, dimension, difference_key)
        if any(not isinstance(value, str) or not value for value in candidate):
            raise ValueError(f"duplicate or incomplete parity delta target: {candidate!r}")
        assert isinstance(form_id, str)
        assert isinstance(dimension, str)
        assert isinstance(difference_key, str)
        exact = (form_id, dimension, difference_key)
        if exact in exact_targets:
            raise ValueError(f"duplicate or incomplete parity delta target: {exact!r}")
        exact_targets.add(exact)
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id or record_id in ids:
            raise ValueError(f"duplicate or missing parity delta id: {record_id!r}")
        ids.add(record_id)
        semantic = target.get("semanticTarget")
        if not isinstance(semantic, dict) or not semantic.get("kind") or not semantic.get("value"):
            raise ValueError(f"{record_id} lacks a stable semantic target")
        references = record.get("evidenceReferences")
        assertion = record.get("differentialAssertion")
        if not references or not assertion:
            raise ValueError(f"{record_id} lacks differential evidence")
        reference_ids: set[str] = set()
        for reference in references:
            reference_id = reference.get("id")
            if (
                not isinstance(reference_id, str)
                or not reference_id
                or reference_id in reference_ids
            ):
                raise ValueError(f"{record_id} has duplicate or missing evidence reference ids")
            reference_ids.add(reference_id)
            if (
                reference.get("repository") != verification["repository"]
                or reference.get("revision") != verification["revision"]
            ):
                raise ValueError(f"{record_id} evidence does not match the offline receipt pin")
            evidence_path = reference.get("path")
            if evidence_path not in verified_paths:
                raise ValueError(f"{record_id} evidence path is absent from the offline receipt")
            used_verified_paths.add(evidence_path)
        if assertion.get("evidenceReferenceId") not in reference_ids:
            raise ValueError(f"{record_id} differential assertion does not join its evidence")
        review = record.get("review", {})
        if review.get("status") == "accepted" and (
            not review.get("reviewer")
            or not review.get("reviewedAt")
            or not review.get("decisionEvidence")
        ):
            raise ValueError(f"{record_id} accepted review lacks durable decision evidence")
        if review.get("status") == "accepted":
            raise ValueError(
                f"{record_id} accepted review requires an independent decision-artifact receipt"
            )
        if review.get("status") not in {"proposed", "accepted", "rejected"}:
            raise ValueError(f"{record_id} has unsupported review status")
        if (
            record.get("classification") == "unresolved_mismatch"
            and review.get("status") == "accepted"
        ):
            raise ValueError(f"{record_id} accepts an unresolved mismatch")
    unused_receipt_paths = sorted(set(verified_paths) - used_verified_paths)
    if unused_receipt_paths:
        raise ValueError(f"parity delta evidence receipt has unused paths: {unused_receipt_paths}")
    source = {
        "repository": selection["source"]["repository"],
        "revision": selection["source"]["revision"],
        "sha256": source_record["sha256"],
        "schemaSha256": schema_record["sha256"],
        "evidenceReceiptSha256": receipt_record["sha256"],
    }
    return ledger, source


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


def revision_attribution(
    *, consumer_revision: str | None = None, pr_head_revision: str | None = None
) -> dict[str, str]:
    """Record both the tested checkout and the PR head without conflating them."""
    tested_revision = _validated_revision(
        consumer_revision if consumer_revision is not None else _consumer_revision()
    )
    resolved_pr_head = _validated_revision(
        pr_head_revision if pr_head_revision is not None else tested_revision
    )
    return {
        "revision": tested_revision,
        "testedRevision": tested_revision,
        "prHeadRevision": resolved_pr_head,
    }


def no_oracle_disposition(
    portable_form_id: str,
    *,
    cohort_path: Path = COHORT_PATH,
    consumer_revision: str | None = None,
    pr_head_revision: str | None = None,
) -> dict[str, Any]:
    """Emit an explicit machine-readable outcome when no comparison oracle exists."""
    return {
        "contract": DISPOSITION_CONTRACT,
        "portableFormId": portable_form_id,
        "outcome": "no_oracle",
        "reasonCode": "no-versioned-oracle-configured",
        "reason": "the differential cohort has no versioned Simpler oracle configured for this form",
        "source": {
            "repository": "https://github.com/mikec-ai/simpler-grants-gov",
            **revision_attribution(
                consumer_revision=consumer_revision, pr_head_revision=pr_head_revision
            ),
            "cohortSha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
        },
    }


def compare_cohort(
    cohort_path: Path = COHORT_PATH,
    *,
    consumer_revision: str | None = None,
    pr_head_revision: str | None = None,
    form_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Compare every declaratively selected form through the same mechanism."""
    cohort = _load_cohort(cohort_path)
    requested_form_ids = tuple(form_ids) if form_ids is not None else None
    if requested_form_ids is not None:
        if len(requested_form_ids) != len(set(requested_form_ids)):
            raise ValueError("differential form selection contains duplicate portable form ids")
        available_form_ids = {record["portableFormId"] for record in cohort["forms"]}
        unknown_form_ids = sorted(set(requested_form_ids) - available_form_ids)
        if unknown_form_ids:
            raise ValueError(
                "differential form selection is outside the cohort: " + ", ".join(unknown_form_ids)
            )
        if not requested_form_ids:
            raise ValueError("differential form selection cannot be empty")
    ledger, ledger_source = _load_delta_ledger()
    source = {
        "repository": "https://github.com/mikec-ai/simpler-grants-gov",
        **revision_attribution(
            consumer_revision=consumer_revision, pr_head_revision=pr_head_revision
        ),
        "cohortSha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
        "deltaLedger": ledger_source,
    }
    receipts: list[dict[str, Any]] = []
    forms_root = Path(forms_package.__file__).parent
    cohort_form_ids = {record["portableFormId"] for record in cohort["forms"]}
    ledger_form_ids = {record["formId"] for record in ledger["records"]}
    extra_ledger_forms = sorted(ledger_form_ids - cohort_form_ids)
    if extra_ledger_forms:
        raise ValueError(
            f"parity delta ledger contains forms outside the cohort: {extra_ledger_forms}"
        )
    selected_records = (
        cohort["forms"]
        if requested_form_ids is None
        else [
            record
            for form_id in requested_form_ids
            for record in cohort["forms"]
            if record["portableFormId"] == form_id
        ]
    )
    for record in selected_records:
        portable_id = record["portableFormId"]
        existing = load_versioned_form(
            forms_root / record["existingDirectory"], record["existingVersion"]
        )
        portable = load_form(portable_id)
        portable_schema = resolve_jsonschema(copy.deepcopy(portable.form_json_schema))
        existing_schema = resolve_jsonschema(copy.deepcopy(existing.FORM_JSON_SCHEMA))
        declared = {
            dimension: {
                delta["target"]["differenceKey"]: delta
                for delta in ledger["records"]
                if delta["formId"] == portable_id and delta["target"]["dimension"] == dimension
            }
            for dimension in ("schema", "ui", "validation", "rules")
        }
        schema = _dimension(
            _schema_differences(
                portable_schema,
                existing_schema,
                portable.form_ui_schema,
                existing.FORM_UI_SCHEMA,
            ),
            declared["schema"],
        )
        ui = _dimension(
            _deep_differences(portable.form_ui_schema, existing.FORM_UI_SCHEMA),
            declared["ui"],
        )
        case_count, validation_differences = _validation_differences(
            portable_schema, existing_schema
        )
        validation = _dimension(
            validation_differences, declared["validation"], caseCount=case_count
        )
        portable_rules = portable.form_rule_schema
        existing_rules = getattr(existing, "FORM_RULE_SCHEMA", None)
        if portable_rules is None and existing_rules is None:
            rules = (
                _dimension([], declared["rules"], comparison="declaration")
                if declared["rules"]
                else {
                    "status": "not_applicable",
                    "reason": "neither implementation declares a rule schema",
                }
            )
        else:
            rules = _dimension(
                _deep_differences(portable_rules, existing_rules),
                declared["rules"],
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
                    dimension["status"] in {"parity", "reviewed_delta", "not_applicable"}
                    for dimension in dimensions.values()
                ),
            }
        )
    return receipts

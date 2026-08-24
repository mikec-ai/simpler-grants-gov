from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.db.models.competition_models import Form
from src.form_schema.form_spec.projection import Projection
from src.form_schema.form_spec.response_normalization import (
    CONTRACT,
    OPERATION,
    ResponseNormalizationOperation,
    ResponseNormalizationPolicy,
    load_response_normalization,
    merge_rule_response,
    normalize_response,
)
from src.services.applications import application_validation


def _write_package(root: Path) -> tuple[dict, dict, Path, Path]:
    manifest = {
        "form": {"id": "arbitrary-form", "formVersion": "7.3"},
        "artifacts": {"evidence.json": "passthrough"},
    }
    evidence = {
        "sources": [
            {
                "id": "official-xsd",
                "type": "xsd",
                "uri": "https://example.gov/arbitrary-v7.3.xsd",
                "nativeVersion": "7.3",
                "sha256": "a" * 64,
            }
        ],
        "responseNormalizationEvidence": [
            {
                "id": "reviewed-omission",
                "canonicalPath": "/optionalNarrative",
                "operation": OPERATION,
                "authority": "official_source",
                "reviewStatus": "reviewed",
                "sourceEvidence": [
                    {
                        "sourceId": "official-xsd",
                        "sourcePath": "Example.OptionalNarrative",
                        "sourceRecord": "The optional element rejects an empty present value.",
                    }
                ],
            }
        ],
    }
    document = {
        "contract": CONTRACT,
        "form": manifest["form"],
        "operations": [
            {
                "path": "/optionalNarrative",
                "operation": OPERATION,
                "evidenceRef": "reviewed-omission",
            }
        ],
    }
    evidence_path = root / "evidence.json"
    evidence_path.write_text(json.dumps(evidence))
    normalization_path = root / "response-normalization.json"
    payload = (json.dumps(document, indent=2) + "\n").encode()
    normalization_path.write_bytes(payload)
    manifest["artifacts"]["response-normalization.json"] = {
        "origin": "passthrough",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    return manifest, evidence, evidence_path, normalization_path


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {"optional_narrative": {"type": "string", "minLength": 1, "maxLength": 50}},
    }


def test_loads_and_projects_a_synthetic_exact_path(tmp_path: Path) -> None:
    manifest, _, _, _ = _write_package(tmp_path)

    policy = load_response_normalization(
        tmp_path,
        manifest=manifest,
        projected_schema=_schema(),
        projection=Projection(),
    )

    assert policy == ResponseNormalizationPolicy(
        CONTRACT,
        (ResponseNormalizationOperation("/optional_narrative", OPERATION, "reviewed-omission"),),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda manifest, evidence, document: manifest["artifacts"][
                "response-normalization.json"
            ].update({"sha256": "0" * 64}),
            "digest does not match",
        ),
        (
            lambda manifest, evidence, document: document.update({"contract": "unknown/v1"}),
            "unsupported response normalization contract",
        ),
        (
            lambda manifest, evidence, document: document["form"].update({"id": "other"}),
            "identity does not match",
        ),
        (
            lambda manifest, evidence, document: document["operations"][0].update(
                {"path": "optionalNarrative"}
            ),
            "invalid response normalization path",
        ),
        (
            lambda manifest, evidence, document: document["operations"][0].update(
                {"operation": "trim"}
            ),
            "unsupported response normalization operation",
        ),
        (
            lambda manifest, evidence, document: document["operations"][0].update(
                {"evidenceRef": "missing"}
            ),
            "unresolved response normalization evidenceRef",
        ),
        (
            lambda manifest, evidence, document: evidence["responseNormalizationEvidence"][
                0
            ].update({"reviewStatus": "unreviewed"}),
            "does not exactly review",
        ),
        (
            lambda manifest, evidence, document: evidence["responseNormalizationEvidence"][0][
                "sourceEvidence"
            ][0].update({"sourceId": "missing"}),
            "names missing source",
        ),
        (
            lambda manifest, evidence, document: evidence["sources"][0].update(
                {"type": "implementation"}
            ),
            "uses implementation evidence as official source",
        ),
    ],
)
def test_loader_fails_closed_on_invalid_package_graph(
    tmp_path: Path, mutation, message: str
) -> None:
    manifest, evidence, evidence_path, normalization_path = _write_package(tmp_path)
    document = json.loads(normalization_path.read_text())
    mutation(manifest, evidence, document)
    evidence_path.write_text(json.dumps(evidence))
    if document != json.loads(normalization_path.read_text()):
        payload = (json.dumps(document, indent=2) + "\n").encode()
        normalization_path.write_bytes(payload)
        if manifest["artifacts"]["response-normalization.json"]["sha256"] != "0" * 64:
            manifest["artifacts"]["response-normalization.json"]["sha256"] = hashlib.sha256(
                payload
            ).hexdigest()

    with pytest.raises(ValueError, match=message):
        load_response_normalization(
            tmp_path,
            manifest=manifest,
            projected_schema=_schema(),
            projection=Projection(),
        )


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"type": "object", "properties": {}}, "does not resolve exactly"),
        (
            {"type": "object", "properties": {"optional_narrative": {"type": "integer"}}},
            "non-null string",
        ),
        (
            {
                "type": "object",
                "properties": {"optional_narrative": {"type": ["string", "null"], "minLength": 1}},
            },
            "non-null string",
        ),
        (
            {
                "type": "object",
                "required": ["optional_narrative"],
                "properties": {"optional_narrative": {"type": "string", "minLength": 1}},
            },
            "required property",
        ),
        (
            {
                "type": "object",
                "properties": {"optional_narrative": {"type": "string", "minLength": 0}},
            },
            "must reject a present empty string",
        ),
    ],
)
def test_loader_rejects_ineligible_projected_targets(
    tmp_path: Path, schema: dict, message: str
) -> None:
    manifest, _, _, _ = _write_package(tmp_path)
    with pytest.raises(ValueError, match=message):
        load_response_normalization(
            tmp_path,
            manifest=manifest,
            projected_schema=schema,
            projection=Projection(),
        )


def test_exact_empty_normalization_is_immutable_idempotent_and_narrow() -> None:
    policy = ResponseNormalizationPolicy(
        CONTRACT,
        (
            ResponseNormalizationOperation("/empty", OPERATION, "a"),
            ResponseNormalizationOperation("/nested/empty", OPERATION, "b"),
        ),
    )
    raw = {
        "empty": "",
        "nested": {"empty": "", "space": " "},
        "undeclared": "",
        "null": None,
        "false": False,
        "zero": 0,
    }
    original = copy.deepcopy(raw)

    normalized = normalize_response(raw, policy)

    assert raw == original
    assert normalized == {
        "nested": {"space": " "},
        "undeclared": "",
        "null": None,
        "false": False,
        "zero": 0,
    }
    assert normalize_response(normalized, policy) == normalized


def test_runtime_shape_mismatch_fails_closed() -> None:
    policy = ResponseNormalizationPolicy(
        CONTRACT,
        (ResponseNormalizationOperation("/nested/value", OPERATION, "a"),),
    )
    with pytest.raises(ValueError, match="response shape is incompatible"):
        normalize_response({"nested": "not-an-object"}, policy)


def test_persistence_merge_preserves_capture_blank_and_rule_writes() -> None:
    policy = ResponseNormalizationPolicy(
        CONTRACT,
        (ResponseNormalizationOperation("/blank", OPERATION, "a"),),
    )
    raw = {"blank": "", "input": "before"}
    rule_result = {"input": "before", "calculated": "42"}

    merged = merge_rule_response(raw, rule_result, policy)

    assert merged == {"blank": "", "input": "before", "calculated": "42"}
    assert raw == {"blank": "", "input": "before"}
    assert rule_result == {"input": "before", "calculated": "42"}
    assert merge_rule_response(raw, {"blank": "rule-value"}, policy) == {"blank": "rule-value"}


def test_application_rules_and_schema_see_normalized_copy_while_capture_stays_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = ResponseNormalizationPolicy(
        CONTRACT,
        (ResponseNormalizationOperation("/optional", OPERATION, "a"),),
    )
    form = Form(
        form_id=uuid.uuid4(),
        form_name="Arbitrary",
        short_form_name="Arbitrary",
        form_version="1.0",
        agency_code="TEST",
        form_json_schema={
            "type": "object",
            "properties": {"optional": {"type": "string", "minLength": 1}},
        },
        form_ui_schema={},
        response_normalization=policy,
    )
    application_form = SimpleNamespace(
        application_response={"optional": ""},
        application_form_id=uuid.uuid4(),
        form_id=form.form_id,
        form=form,
        competition_form=SimpleNamespace(is_required=True),
        application_form_status=None,
    )
    observed: list[dict] = []

    def inspect_context(context) -> None:
        observed.append(copy.deepcopy(context.json_data))
        context.json_data["calculated"] = "rule-write"

    monkeypatch.setattr(application_validation, "process_rule_schema_for_context", inspect_context)

    errors = application_validation.validate_application_form(
        application_form,
        application_validation.ApplicationAction.GET,
    )

    assert errors == []
    assert observed == [{}]
    assert application_form.application_response == {
        "optional": "",
        "calculated": "rule-write",
    }

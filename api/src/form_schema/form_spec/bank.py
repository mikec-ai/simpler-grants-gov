"""Register the question bank with this codebase's JSON Schema resolver.

The bank is published as **one** shared schema document, nested by block id, so a
reference into it is an ordinary JSON pointer:

    https://files.simpler.grants.gov/schemas/question_bank_v1.json#/poc/details

That is deliberately the same mechanism `common_shared_v1` and `address_shared_v1`
already use -- a document of named definitions, referenced by pointer, resolved offline
by `jsonschema_resolver._loader`. The bank is those schemas one level up in granularity:
semantic questions rather than primitives. Consequences:

* Publishing the bank is a registration change. `form_template_registry` already
  dereferences every form at registration time, so the API, the renderer, the validator,
  and XML generation keep receiving the same fully inlined schema they receive today.
* A block's cross-references become same-document pointers (`#/generics/person-name`),
  exactly like `address_shared_v1`'s `{"$ref": "#/street1"}`.
* No custom keyword carries question identity. The pointer *is* the identity.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
from pathlib import Path
from typing import Any

from src.form_schema.form_spec.projection import Projection, project_schema
from src.form_schema.shared.shared_schema import SharedSchema, get_shared_schema_config

#: Emitted artifacts selected from the pinned ``grants-form-spec`` build bundle.
ARTIFACTS = Path(__file__).parent / "artifacts"
ARTIFACT_MANIFEST = ARTIFACTS / "artifact-manifest.json"

BANK_SCHEMA_NAME = "question_bank_v1"


def verify_artifact_selection(*, artifacts: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify one selected artifact tree against its producer-supplied records."""
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("contract") != "grants-form-artifact-selection/v1":
        raise ValueError("unsupported grants form artifact selection contract")

    expected = {
        str(Path(record["path"]).relative_to("dist")): record
        for record in manifest.get("files", [])
    }
    present = {
        str(path.relative_to(artifacts))
        for path in artifacts.rglob("*.json")
        if path != manifest_path
    }
    if present != set(expected):
        missing = sorted(set(expected) - present)
        unexpected = sorted(present - set(expected))
        raise ValueError(f"artifact selection mismatch; missing={missing}, unexpected={unexpected}")

    for relative, record in expected.items():
        payload = (artifacts / relative).read_bytes()
        if len(payload) != record["size"]:
            raise ValueError(f"artifact size mismatch: {relative}")
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise ValueError(f"artifact digest mismatch: {relative}")
    return manifest


@functools.cache
def verify_artifacts() -> dict[str, Any]:
    """Fail closed if a vendored runtime artifact differs from its source manifest."""
    return verify_artifact_selection(artifacts=ARTIFACTS, manifest_path=ARTIFACT_MANIFEST)


def bank_uri() -> str:
    """The bank document's URI, honouring the configured shared-schema base."""
    base = get_shared_schema_config().shared_schema_base_uri.rstrip("/")
    return f"{base}/{BANK_SCHEMA_NAME}.json"


def question_bank_ref(block_id: str) -> str:
    """The reference a form uses to compose a bank question."""
    return f"{bank_uri()}#/{block_id}"


def _block_index() -> dict[str, str]:
    """Canonical artifact path -> block id, for every published block."""
    index: dict[str, str] = {}
    for kind in ("question-bank", "forms"):
        root = ARTIFACTS / kind
        if not root.is_dir():
            continue
        for schema_path in sorted(root.rglob("schema.json")):
            block_id = str(schema_path.parent.relative_to(root))
            index[f"{kind}/{block_id}/schema.json"] = block_id
    return index


@functools.cache
def _bank_projection() -> Projection:
    """A projection that knows every block, so refs and composition can be resolved."""
    verify_artifacts()
    index = _block_index()
    blocks = {
        block_id: json.loads((ARTIFACTS / path).read_text())
        for path, block_id in index.items()
        if path.startswith("question-bank/")
    }
    return Projection(
        bank_uri=bank_uri(),
        block_ids=index,
        blocks=blocks,
    )


def _within_bank_projection() -> Projection:
    """The same projection, but emitting same-document pointers between blocks."""
    return dataclasses.replace(_bank_projection(), within_bank=True, hoisted_defs={})


def build_bank_document() -> dict[str, Any]:
    """Assemble every bank block into one document, nested by block id."""
    projection = _within_bank_projection()
    document: dict[str, Any] = {}
    for block_id, schema in sorted(projection.blocks.items()):
        node = document
        *parents, leaf = block_id.split("/")
        for parent in parents:
            node = node.setdefault(parent, {})
        node[leaf] = project_schema(schema, projection, local_prefix=block_id)
    assert projection.hoisted_defs is not None
    if projection.hoisted_defs:
        document["$defs"] = projection.hoisted_defs
    return document


QUESTION_BANK_V1 = SharedSchema(
    schema_name=BANK_SCHEMA_NAME,
    json_schema=build_bank_document(),
)

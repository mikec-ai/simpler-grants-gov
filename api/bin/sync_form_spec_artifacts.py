#!/usr/bin/env python3
"""Select one form and its transitive questions from a form-spec artifact bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

SOURCE_CONTRACT = "grants-form-artifacts/v1"
SELECTION_CONTRACT = "grants-form-artifact-selection/v1"
RUNTIME_FORM_FILES = (
    "evidence.json",
    "manifest.json",
    "schema.json",
    "sgg/rule-schema.json",
    "sgg/ui-schema.json",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _references(node: Any) -> list[str]:
    if isinstance(node, list):
        return [ref for item in node for ref in _references(item)]
    if not isinstance(node, dict):
        return []
    found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
    return [*found, *(ref for value in node.values() for ref in _references(value))]


def select_artifacts(
    bundle: Path, forms: str | list[str]
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return the minimal runtime selection for one or more forms."""
    requested = [forms] if isinstance(forms, str) else list(dict.fromkeys(forms))
    if not requested:
        raise ValueError("at least one form is required")
    bundle_bytes = bundle.read_bytes()
    with tarfile.open(bundle, mode="r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        manifest_member = members.pop("artifact-manifest.json", None)
        if manifest_member is None:
            raise ValueError("bundle has no artifact-manifest.json")
        extracted = archive.extractfile(manifest_member)
        assert extracted is not None
        source_manifest = json.load(extracted)
        if source_manifest.get("contract") != SOURCE_CONTRACT:
            raise ValueError(f"unsupported source contract: {source_manifest.get('contract')!r}")

        records = {record["path"]: record for record in source_manifest.get("files", [])}
        if set(members) != set(records):
            raise ValueError("bundle membership does not match its source manifest")

        payloads: dict[str, bytes] = {}
        for name, member in members.items():
            extracted = archive.extractfile(member)
            assert extracted is not None
            payload = extracted.read()
            record = records[name]
            if len(payload) != record["size"] or _sha256(payload) != record["sha256"]:
                raise ValueError(f"source artifact digest mismatch: {name}")
            payloads[name] = payload

    selected = {f"dist/forms/{form}/{name}" for form in requested for name in RUNTIME_FORM_FILES}
    missing = sorted(selected - set(payloads))
    if missing:
        raise ValueError(f"requested forms are missing runtime artifacts: {missing}")

    queue = [f"dist/forms/{form}/schema.json" for form in requested]
    visited: set[str] = set()
    while queue:
        schema_path = queue.pop()
        if schema_path in visited:
            continue
        visited.add(schema_path)
        schema = json.loads(payloads[schema_path])
        for ref in _references(schema):
            if ref.startswith("#"):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(schema_path), ref))
            if not target.startswith("dist/question-bank/"):
                raise ValueError(
                    f"portable schema escapes the question bank: {schema_path} -> {ref}"
                )
            if target not in payloads:
                raise ValueError(f"portable schema reference is missing: {schema_path} -> {target}")
            selected.add(target)
            queue.append(target)

    ordered = sorted(selected)
    selection_manifest = {
        "contract": SELECTION_CONTRACT,
        "source": source_manifest["source"],
        "sourceBundleSha256": _sha256(bundle_bytes),
        "selection": {
            "forms": requested,
            "policy": "form runtime and evidence artifacts plus transitive question-schema closure",
        },
        "files": [records[path] for path in ordered],
    }
    return selection_manifest, {path.removeprefix("dist/"): payloads[path] for path in ordered}


def write_selection(*, target: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    """Replace the adapter-owned artifact directory atomically."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as directory:
        staged = Path(directory) / target.name
        for relative, payload in files.items():
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        (staged / "artifact-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        backup = target.with_name(f".{target.name}.previous")
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            target.rename(backup)
        staged.rename(target)
        if backup.exists():
            shutil.rmtree(backup)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="verified grants-form-spec .tar.gz bundle")
    parser.add_argument(
        "--form", required=True, action="append", help="portable form id to select (repeatable)"
    )
    parser.add_argument("--target", required=True, type=Path, help="adapter artifact directory")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest, files = select_artifacts(args.bundle, args.form)
        write_selection(target=args.target, manifest=manifest, files=files)
    except (OSError, ValueError, tarfile.TarError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(
        "selection:\n"
        "  status: synchronized\n"
        f"  forms[{len(args.form)}]: {','.join(args.form)}\n"
        f"  artifacts: {len(files)}\n"
        f"  revision: {manifest['source']['revision']}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

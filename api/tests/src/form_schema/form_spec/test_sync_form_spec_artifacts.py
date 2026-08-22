from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile

import pytest

from bin.sync_form_spec_artifacts import select_artifacts, write_selection


def _bundle(path, files):
    records = [
        {"path": name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        for name, payload in sorted(files.items())
    ]
    manifest = {
        "contract": "grants-form-artifacts/v1",
        "source": {"repository": "example", "revision": "abc123"},
        "files": records,
    }
    entries = {"artifact-manifest.json": json.dumps(manifest).encode(), **files}
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, payload in entries.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))


def test_selects_only_runtime_files_and_transitive_questions(tmp_path):
    files = {
        "dist/forms/example/manifest.json": b"{}",
        "dist/forms/example/schema.json": b'{"$ref":"../../question-bank/a/schema.json"}',
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
        "dist/forms/example/ui.json": b"[]",
        "dist/question-bank/a/schema.json": b'{"$ref":"../b/schema.json"}',
        "dist/question-bank/b/schema.json": b'{"type":"string"}',
        "dist/question-bank/unrelated/schema.json": b'{"type":"string"}',
    }
    bundle = tmp_path / "bundle.tar.gz"
    _bundle(bundle, files)

    manifest, selected = select_artifacts(bundle, "example")

    assert set(selected) == {
        "forms/example/manifest.json",
        "forms/example/schema.json",
        "forms/example/sgg/rule-schema.json",
        "forms/example/sgg/ui-schema.json",
        "question-bank/a/schema.json",
        "question-bank/b/schema.json",
    }
    assert manifest["source"]["revision"] == "abc123"
    assert manifest["selection"]["form"] == "example"

    target = tmp_path / "artifacts"
    write_selection(target=target, manifest=manifest, files=selected)
    assert (target / "question-bank/b/schema.json").is_file()
    assert not (target / "question-bank/unrelated/schema.json").exists()


def test_rejects_a_reference_outside_the_question_bank(tmp_path):
    files = {
        "dist/forms/example/manifest.json": b"{}",
        "dist/forms/example/schema.json": b'{"$ref":"../../../outside.json"}',
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
        "outside.json": b"{}",
    }
    bundle = tmp_path / "bundle.tar.gz"
    _bundle(bundle, files)

    with pytest.raises(ValueError, match="escapes the question bank"):
        select_artifacts(bundle, "example")

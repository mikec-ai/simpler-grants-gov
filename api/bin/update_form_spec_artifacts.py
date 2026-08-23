#!/usr/bin/env python3
"""Build and ingest a grants-form-spec revision without mutating its checkout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from bin.sync_form_spec_artifacts import (  # ruff: ignore[module-import-not-at-top-of-file]
    XSD_DIRECTORY,
    select_artifacts,
    verify_selected_xsds,
    write_selection,
)

DEFAULT_TARGET = API_ROOT / "src" / "form_schema" / "form_spec" / "artifacts"
SELECTION_CONTRACT = "grants-form-artifact-selection/v1"


def selected_forms(target: Path) -> list[str]:
    """Read the form allowlist from the currently pinned selection."""
    manifest_path = target / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("contract") != SELECTION_CONTRACT:
        raise ValueError("target has no supported artifact selection manifest")
    forms = manifest.get("selection", {}).get("forms")
    if not isinstance(forms, list) or not forms or not all(isinstance(item, str) for item in forms):
        raise ValueError("target artifact selection has no form allowlist")
    return list(dict.fromkeys(forms))


def resolve_revision(producer: Path, revision: str) -> str:
    """Resolve an explicit producer ref to the immutable commit recorded in the bundle."""
    result = subprocess.run(
        ["git", "-C", str(producer), "rev-parse", "--verify", f"{revision}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    resolved = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise ValueError(f"producer revision did not resolve to a full commit: {resolved!r}")
    return resolved


def build_bundle(producer: Path, revision: str, workspace: Path) -> Path:
    """Clone locally at one commit, run producer preflight, and return its verified bundle."""
    source = workspace / "grants-form-spec"
    subprocess.run(
        ["git", "clone", "--no-hardlinks", "--quiet", "--no-checkout", str(producer), str(source)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source), "checkout", "--detach", "--quiet", revision], check=True
    )
    subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=source, check=True)
    subprocess.run(["npm", "run", "preflight"], cwd=source, check=True)
    bundle = source / "build" / "grants-form-artifacts.tar.gz"
    if not bundle.is_file():
        raise ValueError("producer preflight did not create an artifact bundle")
    return bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", required=True, type=Path, help="grants-form-spec checkout")
    parser.add_argument("--revision", required=True, help="producer commit or ref to pin")
    parser.add_argument(
        "--form",
        action="append",
        help="portable form id to select; omit to preserve the current allowlist",
    )
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        producer = args.producer.resolve(strict=True)
        revision = resolve_revision(producer, args.revision)
        forms = list(dict.fromkeys(args.form)) if args.form else selected_forms(args.target)
        with tempfile.TemporaryDirectory(prefix="form-spec-update-") as directory:
            bundle = build_bundle(producer, revision, Path(directory))
            manifest, files = select_artifacts(bundle, forms)
            if manifest["source"]["revision"] != revision:
                raise ValueError(
                    "producer bundle revision mismatch: "
                    f"expected {revision}, got {manifest['source']['revision']}"
                )
            verify_selected_xsds(files, xsd_directory=XSD_DIRECTORY)
            write_selection(target=args.target, manifest=manifest, files=files)
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    sys.stdout.write(
        "update:\n"
        "  status: synchronized\n"
        f"  revision: {revision}\n"
        f"  forms[{len(forms)}]: {','.join(forms)}\n"
        f"  artifacts: {len(files)}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

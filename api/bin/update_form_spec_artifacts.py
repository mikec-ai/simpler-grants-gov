#!/usr/bin/env python3
"""Build and ingest a grants-form-spec revision without mutating its checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

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
PROMOTION_RECEIPT_CONTRACT = "sgg-form-spec-promotion/v1"
FORM_ID = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")


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


def promotion_forms(
    target: Path,
    *,
    exact: list[str] | None = None,
    add: list[str] | None = None,
    add_csv: str | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve an exact or additive selection and report newly added form ids.

    Routine promotions are additive: they retain the already reviewed consumer selection and
    append requested forms in caller order. ``--form`` remains available for the deliberate
    exact-selection operation used by the lower-level updater.
    """

    additions = list(add or [])
    if add_csv is not None:
        additions.extend(part.strip() for part in add_csv.split(","))
    if exact and additions:
        raise ValueError("--form cannot be combined with additive form options")

    requested = list(exact) if exact else [*selected_forms(target), *additions]
    if not requested:
        raise ValueError("promotion has no forms")
    invalid = [form_id for form_id in requested if FORM_ID.fullmatch(form_id) is None]
    if invalid:
        raise ValueError(f"promotion has invalid form ids: {invalid}")

    forms = list(dict.fromkeys(requested))
    previous = set(selected_forms(target))
    return forms, [form_id for form_id in forms if form_id not in previous]


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


def build_bundle(producer: Path, revision: str, workspace: Path) -> tuple[Path, Path]:
    """Clone at one commit, run producer preflight, and return its bundle and checkout.

    Prefer the checkout's configured origin over a local-path clone. A local checkout may be a
    partial/promisor clone whose object database does not contain blobs fetched by another
    worktree yet; copying that database can produce an apparently successful clone that cannot
    check out the pinned tree. The remote clone is isolated and retrieves the commit's objects
    independently. Repositories without an origin (including local test fixtures) retain the
    local-path fallback.
    """

    source = workspace / "grants-form-spec"
    try:
        clone_source = subprocess.run(
            ["git", "-C", str(producer), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        clone_source = str(producer)
    if not clone_source:
        clone_source = str(producer)
    subprocess.run(
        ["git", "clone", "--quiet", "--no-checkout", clone_source, str(source)],
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
    return bundle, source


def provision_selected_xsds(
    files: dict[str, bytes], *, producer: Path, xsd_directory: Path
) -> list[Path]:
    """Vendor missing declared XSDs from the immutable producer checkout.

    Existing consumer XSDs remain immutable and are checked by ``verify_selected_xsds``.
    A missing XSD is copied only from the producer's pinned official fixtures and only when
    its bytes match the profile's declared SHA-256.
    """

    fixture_root = producer / "tests" / "fixtures" / "grants-gov-xsd"
    additions: dict[Path, bytes] = {}
    suffix = "/targets/grants-gov-xml.json"
    for relative, payload in sorted(files.items()):
        if not relative.endswith(suffix):
            continue
        profile = json.loads(payload)
        xsd = profile.get("xsd")
        if not isinstance(xsd, dict):
            raise ValueError(f"{relative} has no XSD declaration")
        uri = xsd.get("uri")
        expected = xsd.get("sha256")
        if not isinstance(uri, str) or not uri:
            raise ValueError(f"{relative} has no XSD URI")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"{relative} has no valid XSD SHA-256")

        filename = PurePosixPath(unquote(urlparse(uri).path)).name
        if not filename or filename in {".", ".."}:
            raise ValueError(f"{relative} XSD URI has no filename: {uri}")
        destination = xsd_directory / filename
        if destination.is_file():
            continue

        candidates = sorted(fixture_root.rglob(filename)) if fixture_root.is_dir() else []
        matching = [
            candidate
            for candidate in candidates
            if hashlib.sha256(candidate.read_bytes()).hexdigest() == expected
        ]
        if not matching:
            raise ValueError(
                f"{relative} requires XSD {filename} at {expected}, but the pinned producer "
                "checkout has no matching official fixture"
            )
        candidate_payload = matching[0].read_bytes()
        if destination in additions and additions[destination] != candidate_payload:
            raise ValueError(f"selected XML profiles declare conflicting XSDs for {filename}")
        additions[destination] = candidate_payload

    for destination, payload in additions.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staged:
            staged.write(payload)
            staged_path = Path(staged.name)
        staged_path.replace(destination)
    return sorted(additions)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", required=True, type=Path, help="grants-form-spec checkout")
    parser.add_argument("--revision", required=True, help="producer commit or ref to pin")
    parser.add_argument(
        "--form",
        action="append",
        help="portable form id in an exact replacement selection (repeatable)",
    )
    parser.add_argument(
        "--add-form",
        action="append",
        help="portable form id to append while preserving the current allowlist (repeatable)",
    )
    parser.add_argument(
        "--add-forms",
        help="comma-separated portable form ids to append while preserving the current allowlist",
    )
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--receipt",
        type=Path,
        help="optional path for a machine-readable promotion receipt",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        producer = args.producer.resolve(strict=True)
        revision = resolve_revision(producer, args.revision)
        forms, added_forms = promotion_forms(
            args.target,
            exact=args.form,
            add=args.add_form,
            add_csv=args.add_forms,
        )
        with tempfile.TemporaryDirectory(prefix="form-spec-update-") as directory:
            bundle, producer_checkout = build_bundle(producer, revision, Path(directory))
            manifest, files = select_artifacts(bundle, forms)
            if manifest["source"]["revision"] != revision:
                raise ValueError(
                    "producer bundle revision mismatch: "
                    f"expected {revision}, got {manifest['source']['revision']}"
                )
            provision_selected_xsds(
                files,
                producer=producer_checkout,
                xsd_directory=XSD_DIRECTORY,
            )
            verify_selected_xsds(files, xsd_directory=XSD_DIRECTORY)
            write_selection(target=args.target, manifest=manifest, files=files)
        if args.receipt is not None:
            receipt = {
                "contract": PROMOTION_RECEIPT_CONTRACT,
                "source": manifest["source"],
                "sourceBundleSha256": manifest["sourceBundleSha256"],
                "addedForms": added_forms,
                "selection": forms,
                "artifactCount": len(files),
                "registrationChanged": False,
            }
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
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
        f"  added[{len(added_forms)}]: {','.join(added_forms)}\n"
        f"  artifacts: {len(files)}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

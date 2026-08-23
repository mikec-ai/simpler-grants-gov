"""Dependency-free integrity checks for portable form artifacts.

This module intentionally lives outside the runtime adapter package so artifact tooling can
use it without importing the API's application dependencies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse


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


def verify_xml_profile_xsd(
    profile: dict[str, Any], *, xsd_directory: Path, source: str = "XML profile"
) -> Path:
    """Verify one profile's declared XSD digest and return the vendored XSD path."""
    xsd = profile.get("xsd")
    if not isinstance(xsd, dict):
        raise ValueError(f"{source} has no XSD declaration")

    uri = xsd.get("uri")
    expected = xsd.get("sha256")
    if not isinstance(uri, str) or not uri:
        raise ValueError(f"{source} has no XSD URI")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{source} has no valid XSD SHA-256")

    filename = PurePosixPath(unquote(urlparse(uri).path)).name
    if not filename or filename in {".", ".."}:
        raise ValueError(f"{source} XSD URI has no filename: {uri}")
    path = xsd_directory / filename
    if not path.is_file():
        raise ValueError(f"{source} requires an unvendored XSD: {filename}")

    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            f"{source} XSD digest mismatch for {filename}: expected {expected}, got {actual}"
        )
    return path


def verify_artifact_xsds(*, artifacts: Path, xsd_directory: Path) -> None:
    """Verify every Grants.gov XML profile present in an artifact selection."""
    for profile_path in sorted(artifacts.glob("forms/*/targets/grants-gov-xml.json")):
        profile = json.loads(profile_path.read_text())
        verify_xml_profile_xsd(
            profile,
            xsd_directory=xsd_directory,
            source=str(profile_path.relative_to(artifacts)),
        )

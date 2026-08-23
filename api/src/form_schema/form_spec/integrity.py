"""Consumer-side integrity checks for portable form artifacts.

Artifact JSON is already pinned by the producer bundle manifest. XML profiles additionally
pin the official XSD they target; this module verifies that pin against Simpler's vendored
schema without downloading anything or knowing any form family.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse


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
    import json

    for profile_path in sorted(
        artifacts.glob("forms/*/targets/grants-gov-xml.json")
    ):
        profile = json.loads(profile_path.read_text())
        verify_xml_profile_xsd(
            profile,
            xsd_directory=xsd_directory,
            source=str(profile_path.relative_to(artifacts)),
        )

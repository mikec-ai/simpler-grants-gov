from __future__ import annotations

import hashlib

import pytest

from src.form_schema.form_spec.integrity import verify_artifact_xsds, verify_xml_profile_xsd


def _profile(filename: str, digest: str) -> dict:
    return {
        "xsd": {
            "uri": f"https://apply.grants.gov/forms/{filename}",
            "sha256": digest,
        }
    }


def test_verifies_profile_against_vendored_xsd(tmp_path):
    payload = b"<schema/>"
    xsd = tmp_path / "Example-V1.0.xsd"
    xsd.write_bytes(payload)

    resolved = verify_xml_profile_xsd(
        _profile(xsd.name, hashlib.sha256(payload).hexdigest()),
        xsd_directory=tmp_path,
    )

    assert resolved == xsd


def test_rejects_profile_when_vendored_xsd_digest_differs(tmp_path):
    xsd = tmp_path / "Example-V1.0.xsd"
    xsd.write_bytes(b"changed")

    with pytest.raises(ValueError, match="XSD digest mismatch"):
        verify_xml_profile_xsd(_profile(xsd.name, "a" * 64), xsd_directory=tmp_path)


def test_verifies_every_profile_in_an_artifact_selection(tmp_path):
    artifacts = tmp_path / "artifacts"
    profile_path = artifacts / "forms" / "example" / "targets" / "grants-gov-xml.json"
    profile_path.parent.mkdir(parents=True)
    xsd_directory = tmp_path / "xsds"
    xsd_directory.mkdir()
    payload = b"<schema/>"
    xsd = xsd_directory / "Example-V1.0.xsd"
    xsd.write_bytes(payload)
    import json

    profile_path.write_text(json.dumps(_profile(xsd.name, hashlib.sha256(payload).hexdigest())))

    verify_artifact_xsds(artifacts=artifacts, xsd_directory=xsd_directory)

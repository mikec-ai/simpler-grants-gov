from __future__ import annotations

import json

import pytest

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.projection import Projection
from src.form_schema.form_spec.xml_profile import project_grants_gov_xml_profile


def test_projects_canonical_source_names_through_the_consumer_projection() -> None:
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "formId": "example",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {
            "default": "https://example.gov/form",
            "glob": "https://example.gov/global",
            "att": "https://example.gov/attachment",
        },
        "root": {
            "element": "Example",
            "namespacePrefix": "Example",
            "attributes": {"FormVersion": "1.0"},
        },
        "attachment": {
            "fields": {
                "fileName": {"element": "OriginalName", "namespace": "att"},
                "mimeType": {"element": "MediaType", "namespace": "att"},
                "fileLocation": {"element": "Location", "namespace": "att"},
                "hashValue": {"element": "Digest", "namespace": "glob"},
            }
        },
        "mapping": {
            "fields": {
                "samUei": {"element": "SAMUEI", "kind": "value"},
                "people": {
                    "element": "People",
                    "kind": "array",
                    "items": {
                        "fields": {
                            "firstName": {"element": "FirstName", "kind": "value"},
                            "file": {"element": "File", "kind": "attachment"},
                        }
                    },
                },
                "districtWrapper": {
                    "element": "CongressionalDistrict",
                    "kind": "group",
                    "fields": {
                        "applicantDistrict": {
                            "element": "ApplicantCongressionalDistrict",
                            "kind": "value",
                            "source": "/applicantDistrict",
                        }
                    },
                },
            }
        },
    }
    projection = Projection(
        renames={
            "samUei": "samuei",
            "people.firstName": "given_name",
        }
    )

    runtime = project_grants_gov_xml_profile(profile, projection)

    assert set(runtime) == {"_xml_config", "samuei", "people", "district_wrapper"}
    assert set(runtime["people"]["items"]) == {"given_name", "file"}
    assert runtime["people"]["items"]["file"]["xml_transform"] == {
        "target": "File",
        "type": "attachment",
    }
    assert runtime["people"]["items"]["file"]["file_name"]["xml_transform"] == {
        "target": "OriginalName",
        "namespace": "att",
    }
    assert runtime["district_wrapper"] == {
        "xml_transform": {"target": "CongressionalDistrict", "type": "group"},
        "applicant_district": {
            "xml_transform": {
                "target": "ApplicantCongressionalDistrict",
                "source": "/applicant_district",
            }
        },
    }


def test_budget_profiles_are_loaded_from_portable_artifacts_not_python_form_modules() -> None:
    profile_path = ARTIFACTS / "forms/rr-budget/targets/grants-gov-xml.json"
    profile = json.loads(profile_path.read_text())

    assert profile["mapping"]["fields"]["samUei"] == {
        "element": "SAMUEI",
        "kind": "value",
    }
    assert "samuei" not in profile["mapping"]["fields"]
    assert "sam_uei" not in profile["mapping"]["fields"]
    assert profile["attachment"]["fields"]["hashValue"] == {
        "element": "HashValue",
        "namespace": "glob",
    }


def test_rejects_an_unknown_profile_contract() -> None:
    with pytest.raises(ValueError, match="unsupported Grants.gov XML profile"):
        project_grants_gov_xml_profile({"contract": "future/v2"}, Projection())


def test_rejects_an_attachment_node_without_portable_wire_fields() -> None:
    profile_path = ARTIFACTS / "forms/rr-budget/targets/grants-gov-xml.json"
    profile = json.loads(profile_path.read_text())
    profile.pop("attachment")

    with pytest.raises(ValueError, match="has no declared wire fields"):
        project_grants_gov_xml_profile(profile, Projection())

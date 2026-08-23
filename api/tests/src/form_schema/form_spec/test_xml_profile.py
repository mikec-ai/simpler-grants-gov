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
                    "itemElement": "Profile",
                    "repeatElementPerItem": True,
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
                            "source": "/districtWrapper/applicant~1District",
                        }
                    },
                },
                "details": {
                    "element": "Details",
                    "kind": "group",
                    "flatten": True,
                    "fields": {
                        "answer": {
                            "element": "Answer",
                            "kind": "value",
                            "source": "/details/answer",
                        }
                    },
                },
                "files": {
                    "element": "Files",
                    "kind": "array",
                    "items": {"node": {"element": "File", "kind": "attachment"}},
                },
            }
        },
    }
    projection = Projection(
        renames={
            "samUei": "samuei",
            "people.firstName": "given_name",
            "districtWrapper.applicant/District": "legacy/district",
        }
    )

    runtime = project_grants_gov_xml_profile(profile, projection)

    assert set(runtime) == {
        "_xml_config",
        "samuei",
        "people",
        "district_wrapper",
        "answer",
        "files",
    }
    assert set(runtime["people"]["items"]) == {"given_name", "file"}
    assert runtime["people"]["xml_transform"] == {
        "target": "People",
        "type": "array",
        "item_wrapper": "Profile",
        "repeat_element_per_item": True,
    }
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
                "source": "/district_wrapper/legacy~1district",
            }
        },
    }
    assert runtime["answer"]["xml_transform"] == {
        "target": "Answer",
        "source": "/details/answer",
    }
    assert runtime["files"]["item"]["xml_transform"] == {
        "target": "File",
        "type": "attachment",
    }


def test_projects_constants_value_maps_and_dynamic_attributes_without_form_logic() -> None:
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "formId": "example",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {"default": "https://example.gov/form"},
        "root": {
            "element": "Example",
            "namespacePrefix": "Example",
            "attributes": {"FormVersion": "1.0"},
        },
        "mapping": {
            "fields": {
                "wire": {
                    "element": "Wire",
                    "kind": "group",
                    "attributes": {
                        "Kind": {
                            "source": "/entityType",
                            "valueMap": {"prime": "Prime", "sub": "SubAwardee"},
                        },
                        "Version": {"constant": "1.0"},
                    },
                    "fields": {
                        "answer": {
                            "element": "Answer",
                            "kind": "value",
                            "source": "/entityType",
                            "valueMap": {"prime": "Y: Yes", "sub": "N: No"},
                        },
                        "metadata": {
                            "element": "Metadata",
                            "kind": "group",
                            "flatten": True,
                            "fields": {
                                "entityType": {
                                    "element": "EntityType",
                                    "kind": "value",
                                    "constant": "Prime",
                                }
                            },
                        },
                    },
                }
            }
        },
    }
    projection = Projection(renames={"entityType": "legacy_entity_type"})

    runtime = project_grants_gov_xml_profile(profile, projection)

    transform = runtime["wire"]["xml_transform"]
    assert transform["attributes"] == {
        "Kind": {
            "source": "/legacy_entity_type",
            "value_transform": {
                "type": "map_values",
                "params": {"mappings": {"prime": "Prime", "sub": "SubAwardee"}},
            },
        },
        "Version": {"static_value": "1.0"},
    }
    assert runtime["wire"]["answer"]["xml_transform"] == {
        "target": "Answer",
        "source": "/legacy_entity_type",
        "value_transform": {
            "type": "map_values",
            "params": {"mappings": {"prime": "Y: Yes", "sub": "N: No"}},
        },
    }
    assert runtime["wire"]["legacy_entity_type"]["xml_transform"] == {
        "target": "EntityType",
        "static_value": "Prime",
    }


@pytest.mark.parametrize(
    "declaration",
    [
        {},
        {"source": "/answer", "constant": "fixed"},
        {"constant": "fixed", "valueMap": {"fixed": "mapped"}},
    ],
)
def test_rejects_ambiguous_portable_attribute_values(declaration: dict[str, object]) -> None:
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "formId": "example",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {"default": "https://example.gov/form"},
        "root": {"element": "Example", "namespacePrefix": "Example", "attributes": {}},
        "mapping": {
            "fields": {
                "answer": {
                    "element": "Answer",
                    "kind": "object",
                    "attributes": {"Kind": declaration},
                    "fields": {},
                }
            }
        },
    }

    with pytest.raises(ValueError, match="portable XML value"):
        project_grants_gov_xml_profile(profile, Projection())


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


def test_projects_one_explicit_container_around_a_leaf() -> None:
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {"default": "https://example.gov/form"},
        "root": {
            "element": "Example",
            "namespacePrefix": "Example",
            "attributes": {},
        },
        "mapping": {
            "fields": {
                "answer": {
                    "element": "Answer",
                    "kind": "value",
                    "namespace": "default",
                    "container": {"element": "Answers", "namespace": "default"},
                }
            }
        },
    }

    runtime = project_grants_gov_xml_profile(profile, Projection())

    assert runtime["answer"] == {
        "xml_transform": {
            "target": "Answer",
            "namespace": "default",
            "container": {"target": "Answers", "namespace": "default"},
        }
    }


@pytest.mark.parametrize("kind", ["object", "group", "array"])
def test_rejects_a_container_on_a_non_leaf_mapping(kind: str) -> None:
    node: dict[str, object] = {
        "element": "Invalid",
        "kind": kind,
        "container": {"element": "Container", "namespace": "default"},
    }
    if kind in {"object", "group"}:
        node["fields"] = {}
    else:
        node["items"] = {"fields": {}}
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {"default": "https://example.gov/form"},
        "root": {
            "element": "Example",
            "namespacePrefix": "Example",
            "attributes": {},
        },
        "mapping": {"fields": {"invalid": node}},
    }

    with pytest.raises(ValueError, match="only value or attachment mappings"):
        project_grants_gov_xml_profile(profile, Projection())


@pytest.mark.parametrize(
    ("container", "message"),
    [
        ("Container", "must be an object"),
        ({"namespace": "default"}, "has no element"),
        ({"element": "Container"}, "has no namespace"),
    ],
)
def test_rejects_an_incomplete_leaf_container(container: object, message: str) -> None:
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {"default": "https://example.gov/form"},
        "root": {
            "element": "Example",
            "namespacePrefix": "Example",
            "attributes": {},
        },
        "mapping": {
            "fields": {
                "answer": {
                    "element": "Answer",
                    "kind": "value",
                    "container": container,
                }
            }
        },
    }

    with pytest.raises(ValueError, match=message):
        project_grants_gov_xml_profile(profile, Projection())


def test_rejects_repeated_outer_mode_without_array_item_wrapper() -> None:
    profile = {
        "contract": "grants-gov-xml-profile/v1",
        "xsd": {"uri": "https://example.gov/form.xsd", "sha256": "a" * 64},
        "namespaces": {"default": "https://example.gov/form"},
        "root": {
            "element": "Example",
            "namespacePrefix": "Example",
            "attributes": {},
        },
        "mapping": {
            "fields": {
                "answers": {
                    "element": "Answers",
                    "kind": "array",
                    "repeatElementPerItem": True,
                    "items": {"fields": {"answer": {"element": "Answer", "kind": "value"}}},
                }
            }
        },
    }

    with pytest.raises(ValueError, match="requires an array mapping with itemElement"):
        project_grants_gov_xml_profile(profile, Projection())

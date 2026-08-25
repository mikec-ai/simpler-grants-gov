"""Generic repeated simple-content XML array behavior."""

from lxml import etree as lxml_etree

from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo


def test_flattened_scalar_array_emits_one_direct_element_per_value() -> None:
    namespace = "http://example.org/enrollment"
    config = {
        "_xml_config": {
            "namespaces": {"default": namespace},
            "xml_structure": {"root_element": "Report", "version": "1.0"},
            "xsd_url": "https://example.org/report.xsd",
        },
        "enrollment_countries": {
            "xml_transform": {
                "target": "EnrollmentCountry",
                "type": "array",
                "namespace": "default",
            },
            "item": {"xml_transform": {"flatten_array_item": True}},
        },
    }

    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={"enrollment_countries": ["USA: UNITED STATES", "CAN: CANADA"]},
            transform_config=config,
        )
    )

    assert response.success, response.error_message
    root = lxml_etree.fromstring(response.xml_data.encode())
    countries = root.findall(f"{{{namespace}}}EnrollmentCountry")
    assert [country.text for country in countries] == [
        "USA: UNITED STATES",
        "CAN: CANADA",
    ]
    assert all(len(country) == 0 for country in countries)


def test_flattened_scalar_array_with_item_element_preserves_one_outer_container() -> None:
    namespace = "http://example.org/exemptions"
    config = {
        "_xml_config": {
            "namespaces": {"default": namespace},
            "xml_structure": {"root_element": "Report", "version": "1.0"},
            "xsd_url": "https://example.org/report.xsd",
        },
        "exemptions": {
            "xml_transform": {
                "target": "ExemptionNumbers",
                "type": "array",
                "namespace": "default",
                "item_wrapper": "ExemptionNumber",
                "item_namespace": "default",
            },
            "item": {
                "xml_transform": {
                    "target": "ExemptionNumber",
                    "namespace": "default",
                }
            },
        },
    }

    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={"exemptions": ["E1", "E2"]},
            transform_config=config,
        )
    )

    assert response.success, response.error_message
    root = lxml_etree.fromstring(response.xml_data.encode())
    containers = root.findall(f"{{{namespace}}}ExemptionNumbers")
    assert len(containers) == 1
    assert [item.text for item in containers[0]] == ["E1", "E2"]


def test_scalar_item_node_propagates_repeated_outer_and_item_attributes() -> None:
    namespace = "http://example.org/repeated"
    config = {
        "_xml_config": {
            "namespaces": {"default": namespace},
            "xml_structure": {"root_element": "Report", "version": "1.0"},
            "xsd_url": "https://example.org/report.xsd",
        },
        "entries": {
            "xml_transform": {
                "target": "Entry",
                "type": "array",
                "namespace": "default",
                "item_wrapper": "Value",
                "item_namespace": "default",
                "repeat_element_per_item": True,
                "item_attributes": {"version": "2"},
            },
            "item": {
                "xml_transform": {
                    "target": "Value",
                    "namespace": "default",
                }
            },
        },
    }

    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={"entries": ["one", "two"]},
            transform_config=config,
        )
    )

    assert response.success, response.error_message
    root = lxml_etree.fromstring(response.xml_data.encode())
    entries = root.findall(f"{{{namespace}}}Entry")
    assert len(entries) == 2
    assert [entry[0].text for entry in entries] == ["one", "two"]
    assert [entry[0].get(f"{{{namespace}}}version") for entry in entries] == ["2", "2"]


def test_attachment_item_node_propagates_repeated_outer_and_item_attributes() -> None:
    namespace = "http://example.org/repeated-attachments"
    attachment_namespace = "http://example.org/attachments"
    global_namespace = "http://example.org/global"
    config = {
        "_xml_config": {
            "namespaces": {
                "default": namespace,
                "att": attachment_namespace,
                "glob": global_namespace,
            },
            "xml_structure": {"root_element": "Report", "version": "1.0"},
            "xsd_url": "https://example.org/report.xsd",
        },
        "documents": {
            "xml_transform": {
                "target": "Document",
                "type": "array",
                "namespace": "default",
                "item_wrapper": "AttachedFile",
                "item_namespace": "att",
                "repeat_element_per_item": True,
                "item_attributes": {"version": "2"},
            },
            "item": {
                "xml_transform": {
                    "target": "AttachedFile",
                    "type": "attachment",
                    "namespace": "att",
                },
                "file_name": {"xml_transform": {"target": "FileName", "namespace": "att"}},
                "mime_type": {"xml_transform": {"target": "MimeType", "namespace": "att"}},
                "file_location": {"xml_transform": {"target": "FileLocation", "namespace": "att"}},
                "hash_value": {"xml_transform": {"target": "HashValue", "namespace": "att"}},
            },
        },
    }
    ids = ["one", "two"]
    attachments = {
        item: AttachmentInfo(
            filename=f"{item}.pdf",
            mime_type="application/pdf",
            file_location=f"./attachments/{item}.pdf",
            hash_value="YWJj",
        )
        for item in ids
    }

    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={"documents": ids},
            transform_config=config,
            attachment_mapping=attachments,
        )
    )

    assert response.success, response.error_message
    root = lxml_etree.fromstring(response.xml_data.encode())
    documents = root.findall(f"{{{namespace}}}Document")
    assert len(documents) == 2
    assert [document[0].get(f"{{{attachment_namespace}}}version") for document in documents] == [
        "2",
        "2",
    ]
    assert [
        document[0].find(f"{{{attachment_namespace}}}FileName").text for document in documents
    ] == ["one.pdf", "two.pdf"]


def test_path_local_namespaces_win_when_array_and_attachment_names_collide() -> None:
    root_namespace = "http://example.org/root"
    study_namespace = "http://example.org/study"
    attachment_namespace = "http://example.org/attachments"
    global_namespace = "http://example.org/global"
    attachment_fields = {
        "file_name": {"xml_transform": {"target": "FileName", "namespace": "att"}},
        "mime_type": {"xml_transform": {"target": "MimeType", "namespace": "att"}},
        "file_location": {"xml_transform": {"target": "FileLocation", "namespace": "att"}},
        "hash_value": {"xml_transform": {"target": "HashValue", "namespace": "glob"}},
    }
    config = {
        "_xml_config": {
            "namespaces": {
                "default": root_namespace,
                "study": study_namespace,
                "att": attachment_namespace,
                "glob": global_namespace,
            },
            "xml_structure": {"root_element": "Report", "version": "1.0"},
            "xsd_url": "https://example.org/report.xsd",
        },
        "root_values": {
            "xml_transform": {
                "target": "ExemptionNumbers",
                "type": "array",
                "namespace": "default",
                "item_wrapper": "ExemptionNumber",
                "item_namespace": "default",
                "repeat_element_per_item": True,
            },
            "item": {"xml_transform": {"target": "ExemptionNumber", "namespace": "default"}},
        },
        "root_file": {
            "xml_transform": {
                "target": "attFile",
                "type": "attachment",
                "namespace": "default",
            },
            **attachment_fields,
        },
        "study": {
            "xml_transform": {
                "target": "Study",
                "type": "nested_object",
                "namespace": "study",
            },
            "values": {
                "xml_transform": {
                    "target": "ExemptionNumbers",
                    "type": "array",
                    "namespace": "study",
                    "item_wrapper": "ExemptionNumber",
                    "item_namespace": "study",
                },
                "item": {"xml_transform": {"target": "ExemptionNumber", "namespace": "study"}},
            },
            "file": {
                "xml_transform": {
                    "target": "attFile",
                    "type": "attachment",
                    "namespace": "study",
                },
                **attachment_fields,
            },
        },
    }
    attachments = {
        attachment_id: AttachmentInfo(
            filename=f"{attachment_id}.pdf",
            mime_type="application/pdf",
            file_location=f"./attachments/{attachment_id}.pdf",
            hash_value="YWJj",
        )
        for attachment_id in ("root-file", "study-file")
    }

    response = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data={
                "root_values": ["E1", "E2"],
                "root_file": "root-file",
                "study": {"values": ["E3"], "file": "study-file"},
            },
            transform_config=config,
            attachment_mapping=attachments,
        )
    )

    assert response.success, response.error_message
    root = lxml_etree.fromstring(response.xml_data.encode())
    root_values = root.findall(f"{{{root_namespace}}}ExemptionNumbers")
    root_file = root.find(f"{{{root_namespace}}}attFile")
    study = root.find(f"{{{study_namespace}}}Study")
    assert len(root_values) == 2
    assert [container[0].text for container in root_values] == ["E1", "E2"]
    assert root_file is not None
    assert root_file.findtext(f"{{{attachment_namespace}}}FileName") == "root-file.pdf"
    assert study is not None
    study_values = study.find(f"{{{study_namespace}}}ExemptionNumbers")
    study_file = study.find(f"{{{study_namespace}}}attFile")
    assert study_values is not None
    assert [node.text for node in study_values] == ["E3"]
    assert study_file is not None
    assert study_file.findtext(f"{{{attachment_namespace}}}FileName") == "study-file.pdf"

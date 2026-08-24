"""Consumer-side XML/XSD evidence for the banked Attachment Form package."""

from __future__ import annotations

from pathlib import Path

from lxml import etree as lxml_etree

from src.form_schema.form_spec.loader import _load_banked_form
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.attachment_form_vectors import OUT_OF_ORDER_RESPONSE

XSD_DIR = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
ATTACHMENT_XSD = XSD_DIR / "AttachmentForm_1_2-V1.2.xsd"
FORM_NAMESPACE = "http://apply.grants.gov/forms/AttachmentForm_1_2-V1.2"


def _attachment_mapping() -> dict[str, AttachmentInfo]:
    return {
        attachment_id: AttachmentInfo(
            filename=f"slot-{slot}.pdf",
            mime_type="application/pdf",
            file_location=f"slot-{slot}.pdf",
            hash_value="YWJjZA==",
        )
        for slot, attachment_id in (
            (1, OUT_OF_ORDER_RESPONSE["att1"]),
            (5, OUT_OF_ORDER_RESPONSE["att5"]),
            (15, OUT_OF_ORDER_RESPONSE["att15"]),
        )
    }


def test_portable_attachment_xml_preserves_slot_order_and_validates_exact_xsd() -> None:
    portable = _load_banked_form("attachment-form", project_xml=True)
    result = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=OUT_OF_ORDER_RESPONSE,
            transform_config=portable.json_to_xml_schema,
            attachment_mapping=_attachment_mapping(),
        )
    )

    assert result.success is True
    assert result.xml_data is not None
    root = lxml_etree.fromstring(result.xml_data.encode())
    ordered_slots = [
        lxml_etree.QName(child).localname
        for child in root
        if lxml_etree.QName(child).namespace == FORM_NAMESPACE
    ]
    assert ordered_slots == ["ATT1", "ATT5", "ATT15"]
    assert (
        root.xpath(
            "string(af:ATT1/af:ATT1File/att:FileName)",
            namespaces={
                "af": FORM_NAMESPACE,
                "att": "http://apply.grants.gov/system/Attachments-V1.0",
            },
        )
        == "slot-1.pdf"
    )

    validation = XSDValidator(XSD_DIR).validate_xml(result.xml_data, ATTACHMENT_XSD)
    assert validation == {
        "valid": True,
        "error_type": None,
        "error_message": None,
        "details": "XML is valid according to XSD schema",
    }

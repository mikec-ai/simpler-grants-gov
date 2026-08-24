from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

from lxml import etree as lxml_etree

import src.services.xml_generation.submission_xml_assembler as assembler_module
from src.constants.lookup_constants import ApplicationFormStatus
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.forms.sf424a import FORM_XML_TRANSFORM_RULES
from src.services.applications.application_validation import (
    ApplicationAction,
    validate_application_form,
)
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.submission_xml_assembler import SubmissionXMLAssembler
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.lifecycle import application_form_for
from tests.src.form_schema.forms import test_sf424a as golden_fixtures


def _response_with_legacy_blanks() -> dict:
    line_item = copy.deepcopy(golden_fixtures.full_valid_activity_line_item_v1_0.__wrapped__())
    response = golden_fixtures.full_valid_json_v1_0.__wrapped__(line_item)
    response.update(
        {
            "direct_charges_explanation": "",
            "indirect_charges_explanation": "",
            "remarks": "",
        }
    )
    return response


def test_sf424a_blanks_pass_modify_get_and_submit_without_rewriting_capture() -> None:
    application_form = application_form_for("sf424a", _response_with_legacy_blanks())

    for action in (
        ApplicationAction.MODIFY,
        ApplicationAction.GET,
        ApplicationAction.SUBMIT,
    ):
        assert validate_application_form(application_form, action) == []
        assert application_form.application_form_status is ApplicationFormStatus.COMPLETE
        assert application_form.application_response["direct_charges_explanation"] == ""
        assert application_form.application_response["indirect_charges_explanation"] == ""
        assert application_form.application_response["remarks"] == ""


def test_sf424a_xml_normalizes_a_copy_and_omits_empty_wrapper(
    monkeypatch,
) -> None:
    form = build_runtime_form("sf424a")
    response = _response_with_legacy_blanks()
    captured = copy.deepcopy(response)
    app_form = SimpleNamespace(form=form, application_response=response)
    assembler = object.__new__(SubmissionXMLAssembler)
    assembler.xml_service = XMLGenerationService()
    assembler.attachment_mapping = None
    monkeypatch.setattr(
        assembler_module,
        "load_xml_transform_config",
        lambda _form_name: FORM_XML_TRANSFORM_RULES,
    )

    xml_string = assembler._generate_form_xml(app_form, pretty_print=True)

    assert app_form.application_response == captured
    root = lxml_etree.fromstring(xml_string.encode("utf-8"))
    namespace = {"sf424a": "http://apply.grants.gov/forms/SF424A-V1.0"}
    assert root.find("sf424a:OtherInformation", namespaces=namespace) is None
    assert root.find(".//sf424a:OtherDirectChargesExplanation", namespaces=namespace) is None
    assert root.find(".//sf424a:OtherIndirectChargesExplanation", namespaces=namespace) is None
    assert root.find(".//sf424a:Remarks", namespaces=namespace) is None

    xsd_directory = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
    validator = XSDValidator(xsd_directory)
    result = validator.validate_xml(xml_string, xsd_directory / "SF424A-V1.0.xsd")
    assert result["valid"], result["error_message"]

    app_form.application_response["remarks"] = "Preserved remarks"
    mixed_capture = copy.deepcopy(app_form.application_response)
    mixed_xml = assembler._generate_form_xml(app_form, pretty_print=True)
    mixed_root = lxml_etree.fromstring(mixed_xml.encode("utf-8"))
    wrapper = mixed_root.find("sf424a:OtherInformation", namespaces=namespace)
    assert wrapper is not None
    remarks = wrapper.find("sf424a:Remarks", namespaces=namespace)
    assert remarks is not None and remarks.text == "Preserved remarks"
    assert wrapper.find("sf424a:OtherDirectChargesExplanation", namespaces=namespace) is None
    assert wrapper.find("sf424a:OtherIndirectChargesExplanation", namespaces=namespace) is None
    assert app_form.application_response == mixed_capture
    mixed_result = validator.validate_xml(mixed_xml, xsd_directory / "SF424A-V1.0.xsd")
    assert mixed_result["valid"], mixed_result["error_message"]

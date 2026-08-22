"""Thin Grants.gov XML profiles around the reusable R&R Budget payload mapping."""

import copy
from typing import Any

from src.form_schema.form_spec.xml.rr_budget import (
    COMMON_NAMESPACES,
    RESEARCH_BUDGET_FIELDS,
    RR_BUDGET_10YR_FORM_NAME,
    RR_BUDGET_10YR_NAMESPACE,
    RR_BUDGET_FORM_NAME,
    RR_BUDGET_NAMESPACE,
)


def build_subaward_budget_xml_profile(
    *,
    form_name: str,
    namespace: str,
    xsd_url: str,
    budget_form_name: str,
    budget_namespace: str,
) -> dict[str, Any]:
    """Build a subaward wrapper; all budget payload fields come from one shared mapping."""
    return {
        "_xml_config": {
            "description": "Grants.gov XML projection for an R&R Subaward Budget form",
            "version": "1.0",
            "form_name": form_name,
            "namespaces": {
                "default": namespace,
                budget_form_name: budget_namespace,
                **COMMON_NAMESPACES,
            },
            "xsd_url": xsd_url,
            "xml_structure": {
                "root_element": form_name,
                "root_namespace_prefix": form_name,
                "root_attributes": {"FormVersion": "3.0"},
            },
        },
        "budget_attachments": {
            "xml_transform": {
                "target": "BudgetAttachments",
                "type": "array",
                "item_wrapper": budget_form_name,
                "item_namespace": budget_form_name,
                "item_attributes": {f"{budget_form_name}:FormVersion": "3.0"},
            },
            "items": copy.deepcopy(RESEARCH_BUDGET_FIELDS),
        },
    }


RR_SUBAWARD_BUDGET_XML_TRANSFORM_RULES = build_subaward_budget_xml_profile(
    form_name="RR_SubawardBudget_3_0",
    namespace="http://apply.grants.gov/forms/RR_SubawardBudget_3_0-V3.0",
    xsd_url=("https://apply07.grants.gov/apply/forms/schemas/RR_SubawardBudget_3_0-V3.0.xsd"),
    budget_form_name=RR_BUDGET_FORM_NAME,
    budget_namespace=RR_BUDGET_NAMESPACE,
)

RR_SUBAWARD_BUDGET_30_XML_TRANSFORM_RULES = build_subaward_budget_xml_profile(
    form_name="RR_SubawardBudget30_3_0",
    namespace="http://apply.grants.gov/forms/RR_SubawardBudget30_3_0-V3.0",
    xsd_url=("https://apply07.grants.gov/apply/forms/schemas/RR_SubawardBudget30_3_0-V3.0.xsd"),
    budget_form_name=RR_BUDGET_FORM_NAME,
    budget_namespace=RR_BUDGET_NAMESPACE,
)

RR_SUBAWARD_BUDGET_10YR_30_XML_TRANSFORM_RULES = build_subaward_budget_xml_profile(
    form_name="RR_SubawardBudget10_30_3_0",
    namespace="http://apply.grants.gov/forms/RR_SubawardBudget10_30_3_0-V3.0",
    xsd_url=("https://apply07.grants.gov/apply/forms/schemas/RR_SubawardBudget10_30_3_0-V3.0.xsd"),
    budget_form_name=RR_BUDGET_10YR_FORM_NAME,
    budget_namespace=RR_BUDGET_10YR_NAMESPACE,
)

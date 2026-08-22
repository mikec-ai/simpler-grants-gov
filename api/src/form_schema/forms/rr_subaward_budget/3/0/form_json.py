from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.form_spec.xml.rr_subaward_budget import (
    RR_SUBAWARD_BUDGET_XML_TRANSFORM_RULES,
)
from src.form_schema.forms.rr_subaward_budget.config import FORM_INSTRUCTION_ID

RRSubawardBudget_v3_0 = build_runtime_form(
    "rr-subaward-budget",
    form_type=FormType.RR_SUBAWARD_BUDGET,
    form_instruction_id=FORM_INSTRUCTION_ID,
    json_to_xml_schema=RR_SUBAWARD_BUDGET_XML_TRANSFORM_RULES,
)

FORM_JSON_SCHEMA = RRSubawardBudget_v3_0.form_json_schema
FORM_UI_SCHEMA = RRSubawardBudget_v3_0.form_ui_schema
FORM_RULE_SCHEMA = RRSubawardBudget_v3_0.form_rule_schema
FORM_XML_TRANSFORM_RULES = RRSubawardBudget_v3_0.json_to_xml_schema

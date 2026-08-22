from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.form_spec.xml.rr_budget import RR_BUDGET_10YR_XML_TRANSFORM_RULES
from src.form_schema.forms.rr_budget10.config import FORM_INSTRUCTION_ID

RRBudget10_v3_0 = build_runtime_form(
    "rr-budget-10yr",
    form_type=FormType.RR_BUDGET_10,
    form_instruction_id=FORM_INSTRUCTION_ID,
    json_to_xml_schema=RR_BUDGET_10YR_XML_TRANSFORM_RULES,
)

FORM_JSON_SCHEMA = RRBudget10_v3_0.form_json_schema
FORM_UI_SCHEMA = RRBudget10_v3_0.form_ui_schema
FORM_RULE_SCHEMA = RRBudget10_v3_0.form_rule_schema
FORM_XML_TRANSFORM_RULES = RRBudget10_v3_0.json_to_xml_schema

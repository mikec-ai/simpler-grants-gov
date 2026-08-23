from src.form_schema.form_spec.registrations import portable_form

RRBudget10_v3_0 = portable_form("rr-budget-10yr")

FORM_JSON_SCHEMA = RRBudget10_v3_0.form_json_schema
FORM_UI_SCHEMA = RRBudget10_v3_0.form_ui_schema
FORM_RULE_SCHEMA = RRBudget10_v3_0.form_rule_schema
FORM_XML_TRANSFORM_RULES = RRBudget10_v3_0.json_to_xml_schema

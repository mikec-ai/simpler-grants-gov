from pathlib import Path

from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form

_mod = load_versioned_form(Path(__file__).parent, "1.0")
_portable = load_form("key-contacts")
FORM_JSON_SCHEMA = _portable.form_json_schema
FORM_UI_SCHEMA = _portable.form_ui_schema
# No FORM_RULE_SCHEMA — this form has no conditional fields, attachments, or pre/post-population
FORM_XML_TRANSFORM_RULES = _mod.FORM_XML_TRANSFORM_RULES
KeyContacts_v2_0 = _mod.KeyContacts_v2_0
KeyContacts_v2_0.form_json_schema = FORM_JSON_SCHEMA
KeyContacts_v2_0.form_ui_schema = FORM_UI_SCHEMA
KeyContacts_v2_0.form_rule_schema = _portable.form_rule_schema
del _mod
del _portable

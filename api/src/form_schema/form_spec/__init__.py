"""Adapter between the declarative form specification and this codebase's form runtime.

Everything under this package translates *into* SGG. The canonical artifacts emitted by
`form-spec/` know nothing about the shapes here: they are `camelCase`, they compose with
`$ref`, and their conditional logic sits in one place. This package is where those
choices are projected onto the legacy contract — snake-cased keys, `allOf`-wrapped
references, and object composition flattened so that the flat UI-schema pointers this
codebase's renderer expects still resolve.

Nothing in here imports TypeSpec, reaches the network, or knows how the artifacts were
authored. It reads emitted JSON.
"""

from src.form_schema.form_spec.bank import QUESTION_BANK_V1, question_bank_ref
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.projection import (
    Projection,
    project_rule_schema,
    project_schema,
    project_ui_schema,
)

__all__ = [
    "QUESTION_BANK_V1",
    "Projection",
    "load_form",
    "project_rule_schema",
    "project_schema",
    "project_ui_schema",
    "question_bank_ref",
]

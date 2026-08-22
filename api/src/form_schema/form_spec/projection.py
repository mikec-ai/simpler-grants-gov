"""Projection: canonical form artifacts -> the shapes this codebase's runtime expects.

Four transformations, each of them a legacy accommodation rather than a design choice.
They are collected here, in the adapter, precisely so that a different consumer of the
same question bank can project differently without any of this leaking upstream.

1. **Naming.** The canonical artifacts are `camelCase`. This codebase is `snake_case`,
   and a handful of legacy field names are not a mechanical transformation of anything
   (`cfda_number`, `is_delinquent_federal_debt`). The default rule is camel-to-snake; a
   per-form projection file names the exceptions.

2. **`$ref` wrapping.** `jsonref.replace_refs` substitutes the whole object that carries
   a `$ref`, discarding its siblings, so a form cannot put `title` next to a `$ref` and
   expect it to survive. The legacy idiom is `{"allOf": [{"$ref": ...}], "title": ...}`.
   JSON Schema 2020-12 permits the sibling form; the resolver here does not.

3. **Object composition flattened.** A block that extends another emits
   `allOf: [{"$ref": <base>}]` at the object level. That is correct JSON Schema, but the
   UI schema addresses fields by flat pointers (`/properties/a/properties/b`), which
   cannot see through an `allOf` branch. So object-level composition is inlined here,
   while property-level `$ref`s -- the ones that carry the bank's reuse -- are kept.

4. **Reference retargeting.** Canonical refs are relative paths inside the artifact tree
   (`../../question-bank/generics/address/schema.json`). They become pointers into the
   single bank document this codebase registers with its resolver.

A fifth, smaller one: a field pinned to a single value is spelled `const` in JSON Schema
2020-12 and `enum` with one member by this codebase. That is not cosmetic -- the validator
reports the keyword that failed and the renderer shows the message, so `const` would tell
an applicant "True was expected" where the form today says "is not one of [True]".

Conditional `allOf` branches (`if`/`then`) are never flattened: they are logic, not
composition, and the runtime consumes them where they are.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# JSON Schema keywords whose value is a map of property name to subschema. Their keys are
# form field names and must be projected; every other mapping's keys must not be.
_PROPERTY_MAPS = ("properties", "patternProperties")
# Keywords whose value is a single subschema.
_SUBSCHEMA = ("items", "additionalProperties", "contains", "not", "if", "then", "else")
# Keywords whose value is a list of subschemas.
_SUBSCHEMA_LIST = ("allOf", "anyOf", "oneOf", "prefixItems")


def snake_case(name: str) -> str:
    """`applicantOrganizationName` -> `applicant_organization_name`."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


@dataclasses.dataclass
class Projection:
    """How one form's canonical artifacts map onto the legacy contract.

    `renames` is keyed by canonical data path with array indices collapsed, so
    `keyContacts.projectRole` addresses the field inside every entry of the list. A bare
    member name is also accepted, and applies wherever that member appears -- which is what a
    legacy naming table usually means: on SF-424-Short, the member the bank calls `phone` is
    spelled `phone_number` in all three places it turns up, and one entry says so. An exact
    path wins over a bare name. Only irregular names need an entry; everything else is
    camel-to-snake.
    """

    renames: dict[str, str] = dataclasses.field(default_factory=dict)
    annotations: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    bank_uri: str = ""
    #: canonical block ref (a relative artifact path) -> block id, e.g. `poc/details`
    block_ids: dict[str, str] = dataclasses.field(default_factory=dict)
    #: block id -> that block's canonical schema, used to inline object composition
    blocks: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    #: True while projecting the bank itself, whose blocks reference each other with
    #: same-document pointers -- the style `address_shared_v1` already uses.
    within_bank: bool = False
    #: Collects `$defs` hoisted out of individual blocks to the bank document's root.
    hoisted_defs: dict[str, Any] | None = None

    def rename(self, path: str, name: str) -> str:
        if path in self.renames:
            return self.renames[path]
        return self.renames.get(name, snake_case(name))

    def block_for(self, ref: str) -> str | None:
        """The block id a canonical `$ref` names, or None if it is a local pointer."""
        if ref.startswith("#"):
            return None
        return self.block_ids.get(_normalize(ref))


def _normalize(ref: str) -> str:
    """Collapse `../` segments so a ref can be matched regardless of where it was written."""
    parts: list[str] = []
    for segment in ref.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
            continue
        parts.append(segment)
    return "/".join(parts)


def _pointer(block_id: str, projection: Projection) -> str:
    """A block id becomes a JSON pointer into the bank document: `poc/details`."""
    if projection.within_bank:
        return f"#/{block_id}"
    return f"{projection.bank_uri}#/{block_id}"


#: JSON type names for the literals a form can pin a field to.
_JSON_TYPE = {bool: "boolean", str: "string", int: "integer", float: "number"}


def project_ui_schema(ui_schema: Any, projection: Projection) -> Any:
    """Rename what a UI schema addresses, leaving its structure alone.

    Three things carry a name here and each is a different kind of name. A `definition`
    pointer and a `fieldList`'s `name` address the schema, so they take the field rename. A
    `section`'s name is a UI identifier rather than a data key, and this codebase's forms do
    not agree on a convention for it -- most are snake-cased, SF-424A's are `SectionA` -- so a
    lowerCamel name is projected and a name written in any other convention is left as it is.
    A `multiField`'s `name` is the widget it hands the section to, and renaming that would ask
    for a component that does not exist.
    """
    if isinstance(ui_schema, list):
        return [project_ui_schema(node, projection) for node in ui_schema]
    if not isinstance(ui_schema, dict):
        return ui_schema

    out: dict[str, Any] = {}
    for key, value in ui_schema.items():
        if key == "definition":
            out[key] = (
                [_project_pointer(p, projection) for p in value]
                if isinstance(value, list)
                else _project_pointer(value, projection)
            )
        elif key == "name":
            kind = ui_schema.get("type")
            if kind == "multiField":
                out[key] = value
            elif kind == "section":
                out[key] = _project_identifier(str(value))
            else:
                out[key] = projection.rename(str(value), str(value))
        elif key == "children":
            out[key] = [project_ui_schema(child, projection) for child in value]
        else:
            out[key] = value
    return out


def _project_identifier(name: str) -> str:
    """A UI identifier: projected when it is lowerCamel, left alone otherwise."""
    return snake_case(name) if name[:1].islower() else name


def _project_pointer(pointer: str, projection: Projection) -> str:
    """`/properties/keyContacts/items/properties/projectRole` -> the projected spelling.

    The data path is the pointer with its `properties` and `items` steps dropped, which is
    what the rename table is keyed by -- so a pointer and the property it addresses are
    always renamed by the same entry.
    """
    if not pointer.startswith("/"):
        return pointer
    steps = pointer.strip("/").split("/")
    out: list[str] = []
    path: list[str] = []
    for step in steps:
        if step in ("properties", "items"):
            out.append(step)
            continue
        path.append(step)
        out.append(projection.rename(".".join(path), step))
    return "/" + "/".join(out)


def project_rule_schema(rules: Any, projection: Projection, path: str = "") -> Any:
    """Rename a rule schema's keys and the field paths its rules reference."""
    if not isinstance(rules, dict):
        return rules

    out: dict[str, Any] = {}
    for key, value in rules.items():
        if key.startswith("gg_"):
            out[key] = _project_rule(value, projection, path)
        elif key == "gg_type":
            out[key] = value
        else:
            here = _join(path, key)
            out[projection.rename(here, key)] = project_rule_schema(value, projection, here)
    return out


def _project_rule(rule: Any, projection: Projection, path: str) -> Any:
    if not isinstance(rule, dict):
        return rule
    out = dict(rule)
    fields = rule.get("fields")
    if isinstance(fields, list):
        out["fields"] = [_project_reference(f, projection, path) for f in fields]
    return out


def _project_reference(reference: str, projection: Projection, path: str) -> str:
    """Rename a calculation's reference, in any of the three spellings SGG uses.

    `@THIS.member` is relative to the object holding the calculation, `a[*].b.c` walks into
    every entry of a list, and a bare dotted path starts at the form's root. All three are
    sequences of field names, so all three are renamed segment by segment against the same
    table.
    """
    prefix = ""
    body = reference
    if body.startswith("@THIS."):
        prefix, body = "@THIS.", body[len("@THIS.") :]
        base = path.split(".")
    else:
        base = []

    renamed: list[str] = []
    walked = list(base)
    for segment in body.split("."):
        marker = ""
        if segment.endswith("[*]"):
            segment, marker = segment[:-3], "[*]"
        walked.append(segment)
        renamed.append(projection.rename(".".join(walked), segment) + marker)
    return prefix + ".".join(renamed)


def project_schema(
    schema: dict[str, Any],
    projection: Projection,
    *,
    path: str = "",
    local_prefix: str = "",
) -> dict[str, Any]:
    """Project one canonical schema document into the legacy shape.

    `local_prefix` is prepended to same-document pointers. It is empty for a form, whose
    `$defs` stay at its own root, and is the block's id for a bank block, whose `$defs`
    are nested one level down once the bank is assembled into a single document.
    """
    projected = _project_node(schema, projection, path, local_prefix)
    projected.pop("$schema", None)
    projected.pop("$id", None)
    if projection.hoisted_defs is not None:
        _hoist_defs(projected, projection.hoisted_defs)
    return projected


def _hoist_defs(node: dict[str, Any], into: dict[str, Any]) -> None:
    """Lift a block's local `$defs` to the bank document's root.

    A shared code list -- state, country -- belongs to the bank, not to whichever
    question happened to declare it. Hoisting keeps one copy per bank document and
    leaves nothing behind for the resolver to carry into every form that composes the
    question.
    """
    defs = node.pop("$defs", None)
    if not defs:
        return
    for name, definition in defs.items():
        existing = into.get(name)
        if existing is not None and existing != definition:
            raise ValueError(
                f"two bank blocks define $defs/{name} differently; give one a distinct name"
            )
        into[name] = definition


def _project_node(
    node: Any,
    projection: Projection,
    path: str,
    local_prefix: str,
    in_condition: bool = False,
) -> Any:
    if isinstance(node, list):
        return [_project_node(item, projection, path, local_prefix, in_condition) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "$ref":
            out[key] = _project_ref(value, projection, local_prefix)
        elif key in _PROPERTY_MAPS:
            projected_properties: dict[str, Any] = {}
            for name, sub in value.items():
                here = _join(path, name)
                projected = _project_node(sub, projection, here, local_prefix, in_condition)
                annotation = None
                if not in_condition:
                    annotation = projection.annotations.get(here) or projection.annotations.get(
                        name
                    )
                if annotation:
                    projected.update(annotation)
                projected_properties[projection.rename(here, name)] = projected
            out[key] = projected_properties
        elif key == "required":
            out[key] = [projection.rename(_join(path, name), name) for name in value]
        elif key == "$defs":
            out[key] = {
                name: _project_node(sub, projection, path, local_prefix, in_condition)
                for name, sub in value.items()
            }
        elif key in _SUBSCHEMA:
            # `const` inside `if` is a test, not a field's value: leave it alone.
            out[key] = _project_node(
                value, projection, path, local_prefix, in_condition or key == "if"
            )
        elif key in _SUBSCHEMA_LIST:
            out[key] = [
                _project_node(item, projection, path, local_prefix, in_condition) for item in value
            ]
        elif key == "dependentRequired":
            out[key] = {
                projection.rename(_join(path, name), name): [
                    projection.rename(_join(path, dep), dep) for dep in deps
                ]
                for name, deps in value.items()
            }
        else:
            out[key] = value

    if not in_condition:
        out = _singleton_enum(out)
    out = _wrap_ref(out, projection)
    return _flatten_composition(out, projection, path, local_prefix)


def _singleton_enum(node: dict[str, Any]) -> dict[str, Any]:
    """`{"const": true}` -> `{"type": "boolean", "enum": [true]}`.

    Transformation 5. Both say the field must hold exactly that value; only the second
    produces the message this codebase's forms produce today.
    """
    if "const" not in node or "enum" in node:
        return node
    node = dict(node)
    value = node.pop("const")
    kind = _JSON_TYPE.get(type(value))
    if kind is not None:
        node.setdefault("type", kind)
    return {**node, "enum": [value]}


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def _project_ref(ref: str, projection: Projection, local_prefix: str) -> str:
    block_id = projection.block_for(ref)
    if block_id is not None:
        return _pointer(block_id, projection)
    if ref.startswith("#/$defs/") and projection.hoisted_defs is not None:
        return ref
    if ref.startswith("#") and local_prefix:
        return f"#/{local_prefix}{ref[1:]}"
    return ref


def _wrap_ref(node: dict[str, Any], projection: Projection) -> dict[str, Any]:
    """`{"$ref": r, "title": t}` -> `{"allOf": [{"$ref": r}], "title": t}`.

    Transformation 2. Two reasons to wrap:

    * The resolver substitutes the whole object carrying a `$ref` and would otherwise
      discard `title` and everything else beside it.
    * A reference to a bank question is wrapped even with nothing beside it, because that
      is the shape this codebase's forms already ship, and a sibling added later must not
      silently start disappearing.

    A local pointer with no siblings is left alone: `items: {"$ref": "#/$defs/..."}` must
    stay addressable at `items/properties/...` for the UI schema's flat pointers.
    """
    ref = node.get("$ref")
    if ref is None:
        return node
    if len(node) == 1 and _block_pointer(ref, projection) is None:
        return node
    node = dict(node)
    node.pop("$ref")
    existing = node.pop("allOf", [])
    return {"allOf": [{"$ref": ref}, *existing], **node}


def _block_pointer(ref: str, projection: Projection) -> str | None:
    """The block id a *projected* reference names, or None if it names something else."""
    prefix = "#/" if projection.within_bank else projection.bank_uri + "#/"
    if not ref.startswith(prefix):
        return None
    block_id = ref[len(prefix) :]
    return block_id if block_id in projection.blocks else None


def _flatten_composition(
    node: dict[str, Any],
    projection: Projection,
    path: str,
    local_prefix: str,
) -> dict[str, Any]:
    """Inline object-level `allOf` composition so flat UI pointers can reach the fields.

    Transformation 3. A branch is composition when it is a reference to a known block and
    the node declares its own `properties` -- that is the signature of `extends`. A branch
    carrying `if` is conditional logic and is left where it is.
    """
    branches = node.get("allOf")
    is_object = node.get("type") == "object" or "properties" in node
    if not isinstance(branches, list) or not is_object:
        return node

    kept: list[Any] = []
    merged_properties: dict[str, Any] = {}
    merged_required: list[str] = []

    for branch in branches:
        block_id = _composed_block(branch, projection)
        if block_id is None:
            kept.append(branch)
            continue
        base = project_schema(
            projection.blocks[block_id],
            projection,
            path=path,
            local_prefix=local_prefix,
        )
        merged_properties.update(base.get("properties", {}))
        merged_required.extend(base.get("required", []))
        if base.get("$defs"):
            # Hoisting a base's local definitions would need its `#/$defs/...` pointers
            # rebased onto the extending document. No block needs it yet, and guessing
            # would be worse than saying so.
            raise NotImplementedError(
                f"cannot inline block {block_id!r}: it declares $defs, which would need "
                "pointer rebasing in the extending document"
            )
        kept.extend(base.get("allOf", []))

    if not merged_properties and not merged_required:
        return node

    # The base's members come first: they are the question, and the extension adds to it.
    node["properties"] = {**merged_properties, **node.get("properties", {})}
    if merged_required or node.get("required"):
        combined = merged_required + [
            name for name in node.get("required", []) if name not in merged_required
        ]
        node["required"] = combined
    if kept:
        node["allOf"] = kept
    else:
        node.pop("allOf")
    return node


def _composed_block(branch: Any, projection: Projection) -> str | None:
    if not isinstance(branch, dict):
        return None
    # `_wrap_ref` has already run on the branch, so a bare reference now looks like
    # `{"allOf": [{"$ref": ...}]}`. Either spelling is composition.
    if set(branch) == {"allOf"} and len(branch["allOf"]) == 1:
        branch = branch["allOf"][0]
    if not isinstance(branch, dict) or set(branch) != {"$ref"}:
        return None
    return _block_pointer(branch["$ref"], projection)

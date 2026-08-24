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
_ARRAY_MARKER = re.compile(r"^(?P<name>.*?)(?P<marker>\[(?:\*|\d+)\])?$")
_MATERIALIZABLE_CALCULATION_RULES = {
    "sum_monetary",
    "sum_integer",
    "subtract_monetary",
    "multiply_by_percentage",
}

# JSON Schema keywords whose value is a map of property name to subschema. Their keys are
# form field names and must be projected; every other mapping's keys must not be.
_PROPERTY_MAPS = ("properties",)
# Keywords whose value is a single subschema.
_SUBSCHEMA = ("items", "additionalProperties", "contains", "not", "if", "then", "else")
# Keywords whose value is a list of subschemas.
_SUBSCHEMA_LIST = ("allOf", "anyOf", "oneOf", "prefixItems")

# Grants.gov's authoritative UniversalCodes V2.0 XSD uses a typographic apostrophe for
# this country value. Simpler's existing CountryCode enum, persisted responses, and
# translations use the ASCII spelling. Keep the portable artifact source-faithful and
# adapt only at this consumer boundary so imported forms remain compatible with the
# runtime contract.
_SGG_ENUM_VALUES = {
    "CIV: CÔTE D’IVOIRE": "CIV: CÔTE D'IVOIRE",
}


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
    identifiers: dict[str, str] = dataclasses.field(default_factory=dict)
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
    #: Source-faithful enum literal -> this consumer's established persisted spelling.
    enum_values: dict[str, str] = dataclasses.field(default_factory=lambda: dict(_SGG_ENUM_VALUES))

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
    """Rename what a UI schema addresses, leaving its structure alone."""
    return _project_ui_schema(ui_schema, projection, item_parent=None)


def _project_ui_schema(
    ui_schema: Any,
    projection: Projection,
    *,
    item_parent: list[str] | None = None,
) -> Any:
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
        return [_project_ui_schema(node, projection, item_parent=item_parent) for node in ui_schema]
    if not isinstance(ui_schema, dict):
        return ui_schema

    child_item_parent = item_parent
    definition = ui_schema.get("definition")
    if ui_schema.get("type") == "fieldList" and isinstance(definition, str):
        child_item_parent = _schema_pointer_field_segments(definition)

    out: dict[str, Any] = {}
    for key, value in ui_schema.items():
        if key == "definition":
            out[key] = (
                [_project_schema_pointer(p, projection) for p in value]
                if isinstance(value, list)
                else _project_schema_pointer(value, projection)
            )
        elif key == "name":
            kind = ui_schema.get("type")
            if kind == "multiField":
                out[key] = value
            elif kind == "section":
                out[key] = _project_identifier(str(value), projection)
            elif kind == "fieldList" and isinstance(definition, str):
                fields = _schema_pointer_field_segments(definition)
                path = ".".join(fields)
                out[key] = projection.rename(path, str(value))
            else:
                out[key] = projection.rename(str(value), str(value))
        elif key == "children":
            out[key] = _project_ui_schema(
                value,
                projection,
                item_parent=child_item_parent,
            )
        elif key == "conditional":
            out[key] = _project_ui_conditional(value, projection, item_parent=item_parent)
        else:
            # Table layouts add a nested columns/rows/cells structure under children.
            # Recurse through target-owned presentation metadata so definitions at any
            # supported depth cross the same canonical-to-consumer naming boundary.
            out[key] = _project_ui_schema(
                value,
                projection,
                item_parent=item_parent,
            )
    return out


def _project_ui_conditional(
    conditional: Any,
    projection: Projection,
    *,
    item_parent: list[str] | None,
) -> Any:
    """Project data pointers inside the portable conditional-UI contract.

    Conditional expressions are UI behavior, but their ``ref.pointer`` values address
    form data. They therefore cross the same canonical-to-legacy naming boundary as field
    definitions. All operators and outcomes remain consumer-neutral data.
    """
    if isinstance(conditional, list):
        return [
            _project_ui_conditional(value, projection, item_parent=item_parent)
            for value in conditional
        ]
    if not isinstance(conditional, dict):
        return conditional

    out: dict[str, Any] = {}
    for key, value in conditional.items():
        if key == "pointer" and isinstance(value, str):
            parent = item_parent if conditional.get("scope") == "item" else None
            out[key] = project_response_pointer(value, projection, parent=parent)
        else:
            out[key] = _project_ui_conditional(value, projection, item_parent=item_parent)
    return out


def _project_identifier(name: str, projection: Projection) -> str:
    """A UI identifier: projected when it is lowerCamel, left alone otherwise."""
    if name in projection.identifiers:
        return projection.identifiers[name]
    return snake_case(name) if name[:1].islower() else name


def _split_array_marker(segment: str) -> tuple[str, str]:
    """Separate a field name from rule-path array selectors without losing either."""
    match = _ARRAY_MARKER.fullmatch(segment)
    if match is None or "[" in match.group("name") or "]" in match.group("name"):
        raise ValueError(
            "rule path segments support at most one trailing [*] or numeric array selector: "
            f"{segment!r}"
        )
    return match.group("name"), match.group("marker") or ""


def _canonical_segments(path: str) -> list[str]:
    """Return the field ancestry used by path-qualified rename declarations."""
    return [_split_array_marker(segment)[0] for segment in path.split(".") if segment]


def _project_field_segments(
    segments: list[str],
    projection: Projection,
    *,
    parent: list[str] | None = None,
    preserve_indices: bool = False,
    rule_selectors: bool = False,
) -> list[str]:
    """Project field segments against one canonical, segment-aware ancestry.

    UI pointers, rule references, and XML source pointers use different separators and
    structural tokens, but their field segments have the same meaning. Their syntax-specific
    adapters decode into this primitive and encode its result back into their own vocabulary.
    Array selectors are preserved on output and excluded from rename lookup paths.
    """
    walked = list(parent or [])
    projected: list[str] = []
    for raw_segment in segments:
        if preserve_indices and raw_segment.isdecimal():
            projected.append(raw_segment)
            continue
        name, marker = _split_array_marker(raw_segment) if rule_selectors else (raw_segment, "")
        walked.append(name)
        projected.append(projection.rename(".".join(walked), name) + marker)
    return projected


def _decode_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _encode_pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def project_response_pointer(
    pointer: str,
    projection: Projection,
    *,
    parent: list[str] | None = None,
) -> str:
    """Project an absolute JSON Pointer whose every segment is a response field."""
    if not pointer.startswith("/"):
        return pointer
    decoded = [_decode_pointer_segment(segment) for segment in pointer[1:].split("/")]
    projected = _project_field_segments(
        decoded,
        projection,
        parent=parent,
        preserve_indices=True,
    )
    return "/" + "/".join(_encode_pointer_segment(segment) for segment in projected)


def _project_schema_pointer(pointer: str, projection: Projection) -> str:
    """`/properties/keyContacts/items/properties/projectRole` -> the projected spelling.

    Only segments following ``properties`` are field names. Schema vocabulary such as
    ``properties`` and ``items`` is preserved, as are any other non-field identifiers.
    """
    if not pointer.startswith("/"):
        return pointer
    steps = [_decode_pointer_segment(segment) for segment in pointer[1:].split("/")]
    field_positions = _schema_pointer_field_positions(steps)
    projected_fields = iter(
        _project_field_segments([steps[index] for index in field_positions], projection)
    )
    out = list(steps)
    for index in field_positions:
        out[index] = next(projected_fields)
    return "/" + "/".join(_encode_pointer_segment(segment) for segment in out)


def _schema_pointer_field_segments(pointer: str) -> list[str]:
    """Extract canonical field ancestry from an absolute JSON Schema pointer."""
    if not pointer.startswith("/"):
        return []
    steps = [_decode_pointer_segment(segment) for segment in pointer[1:].split("/")]
    return [steps[index] for index in _schema_pointer_field_positions(steps)]


def _schema_pointer_field_positions(steps: list[str]) -> list[int]:
    """Locate fields without mistaking schema keywords or regex keys for field names."""
    field_positions: list[int] = []
    expects_field = False
    for index, step in enumerate(steps):
        if expects_field:
            field_positions.append(index)
            expects_field = False
        elif step == "properties":
            expects_field = True
    return field_positions


def project_rule_schema(rules: Any, projection: Projection, path: str = "") -> Any:
    """Rename a rule schema's keys and the field paths its rules reference."""
    if path == "":
        _validate_rule_schema(rules)
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
    presence_fields = rule.get("presence_fields")
    if isinstance(presence_fields, list):
        out["presence_fields"] = [_project_reference(f, projection, path) for f in presence_fields]
    for key in ("amount", "percentage"):
        reference = rule.get(key)
        if isinstance(reference, str):
            out[key] = _project_reference(reference, projection, path)
    return out


def _validate_rule_schema(node: Any) -> None:
    if isinstance(node, list):
        for value in node:
            _validate_rule_schema(value)
        return
    if not isinstance(node, dict):
        return
    pre_population = node.get("gg_pre_population")
    if isinstance(pre_population, dict) and "materialize" in pre_population:
        rule = pre_population.get("rule")
        if rule not in _MATERIALIZABLE_CALCULATION_RULES:
            raise ValueError(
                "calculation materialization policy requires a supported calculation rule"
            )
        if pre_population["materialize"] != "when_any_source_present":
            raise ValueError(
                f"unknown calculation materialization policy: {pre_population['materialize']!r}"
            )
        presence_fields = pre_population.get("presence_fields")
        if (
            not isinstance(presence_fields, list)
            or not presence_fields
            or not all(isinstance(field, str) and field for field in presence_fields)
        ):
            raise ValueError("when_any_source_present requires non-empty string presence_fields")
        if rule == "multiply_by_percentage":
            if not all(
                isinstance(pre_population.get(key), str) and pre_population[key]
                for key in ("amount", "percentage")
            ):
                raise ValueError(
                    "materialized multiply_by_percentage requires non-empty amount and percentage paths"
                )
        else:
            fields = pre_population.get("fields")
            if (
                not isinstance(fields, list)
                or not fields
                or not all(isinstance(field, str) and field for field in fields)
            ):
                raise ValueError(f"materialized {rule} requires non-empty string fields")
    for value in node.values():
        _validate_rule_schema(value)


def _project_reference(reference: str, projection: Projection, path: str) -> str:
    """Rename a calculation's reference, in any of the three spellings SGG uses.

    `@THIS.member` is relative to the object holding the calculation, `a[*].b.c` walks into
    every entry of a list, and a bare dotted path starts at the form's root. All three are
    sequences of field names, so all three are renamed segment by segment against the same
    table.
    """
    prefix = ""
    body = reference
    base: list[str] = []
    # ``path`` names the target field. @THIS starts at the object holding that target;
    # @PARENT starts one object above it, matching the runtime rule-path vocabulary.
    for relative_prefix, levels_up in (("@THIS.", 1), ("@PARENT.", 2)):
        if body.startswith(relative_prefix):
            prefix, body = relative_prefix, body[len(relative_prefix) :]
            path_segments = _canonical_segments(path)
            base = path_segments[:-levels_up] if levels_up <= len(path_segments) else []
            break

    return prefix + ".".join(
        _project_field_segments(
            body.split("."),
            projection,
            parent=base,
            rule_selectors=True,
        )
    )


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
        elif key == "patternProperties":
            out[key] = {
                pattern: _project_node(sub, projection, path, local_prefix, in_condition)
                for pattern, sub in value.items()
            }
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
        elif key == "enum" and isinstance(value, list):
            out[key] = [projection.enum_values.get(item, item) for item in value]
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
    merged_keywords: dict[str, Any] = {}
    merged_properties: dict[str, Any] = {}
    merged_required: list[str] = []

    for branch in branches:
        base = _composed_base(branch, projection, path, local_prefix)
        if base is None:
            kept.append(branch)
            continue
        merged_keywords.update({
            key: value
            for key, value in base.items()
            if key not in {"properties", "required", "$defs", "allOf"}
        })
        merged_properties.update(base.get("properties", {}))
        merged_required.extend(base.get("required", []))
        if base.get("$defs"):
            # The assembled bank hoists every block's local definitions to its own root.
            # A form that flattens object composition therefore points at that authoritative
            # bank location instead of copying definitions into each resolved form.
            base.pop("$defs")
            base = _rebase_defs_to_bank(base, projection.bank_uri)
            merged_properties = {
                **merged_properties,
                **base.get("properties", {}),
            }
        kept.extend(base.get("allOf", []))

    if not merged_properties and not merged_required:
        return node

    # Composition contributes the base schema's ordinary constraints as well as its
    # members. The overlay remains authoritative for any keyword it explicitly sets.
    node = {**merged_keywords, **node}

    # The base's members come first: they are the question, and the extension adds to it.
    combined_properties = dict(merged_properties)
    for name, patch in node.get("properties", {}).items():
        existing = combined_properties.get(name)
        combined_properties[name] = (
            _merge_subschemas(existing, patch)
            if isinstance(existing, dict) and isinstance(patch, dict)
            else patch
        )
    node["properties"] = combined_properties
    if merged_required or node.get("required"):
        combined = merged_required + [
            name for name in node.get("required", []) if name not in merged_required
        ]
        node["required"] = combined
    if kept:
        node["allOf"] = kept
    else:
        node.pop("allOf")

    # A parent composition can introduce a referenced child and then apply a nested
    # overlay to it. Those two pieces did not coexist when the child was first visited
    # by `_project_node`, so give the newly combined subtree one composition pass now.
    # This is what preserves, for example, a bank question's decimal constraints when a
    # form marks that same question read-only.
    node["properties"] = {
        name: _flatten_introduced_compositions(
            child,
            projection,
            _join(path, name),
            local_prefix,
        )
        for name, child in node["properties"].items()
    }
    return node


def _flatten_introduced_compositions(
    node: Any,
    projection: Projection,
    path: str,
    local_prefix: str,
) -> Any:
    """Flatten compositions created by merging a parent block with its overlay."""
    if isinstance(node, list):
        return [
            _flatten_introduced_compositions(item, projection, path, local_prefix) for item in node
        ]
    if not isinstance(node, dict):
        return node

    # A deep merge can put an overlay beside a reference that was bare when first
    # projected. Wrap it before attempting composition so the legacy resolver cannot
    # discard the overlay and the base definition remains available to inline.
    prepared = _wrap_ref(dict(node), projection) if "$ref" in node and len(node) > 1 else dict(node)
    flattened = _flatten_composition(prepared, projection, path, local_prefix)
    out: dict[str, Any] = {}
    for key, value in flattened.items():
        if key in _PROPERTY_MAPS:
            out[key] = {
                name: _flatten_introduced_compositions(
                    child,
                    projection,
                    _join(path, name),
                    local_prefix,
                )
                for name, child in value.items()
            }
        elif key == "patternProperties":
            out[key] = {
                pattern: _flatten_introduced_compositions(
                    child,
                    projection,
                    path,
                    local_prefix,
                )
                for pattern, child in value.items()
            }
        elif key in _SUBSCHEMA:
            out[key] = _flatten_introduced_compositions(value, projection, path, local_prefix)
        elif key in _SUBSCHEMA_LIST:
            out[key] = [
                _flatten_introduced_compositions(item, projection, path, local_prefix)
                for item in value
            ]
        else:
            out[key] = value
    return out


def _merge_subschemas(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a declarative overlay without erasing the composed block beneath it."""
    result = dict(base)
    for key, value in patch.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _merge_subschemas(existing, value)
        elif key == "allOf" and isinstance(existing, list) and isinstance(value, list):
            result[key] = [*existing, *value]
        else:
            result[key] = value
    return result


def _rebase_defs_to_bank(node: Any, bank_uri: str) -> Any:
    if isinstance(node, list):
        return [_rebase_defs_to_bank(item, bank_uri) for item in node]
    if not isinstance(node, dict):
        return node
    return {
        key: (
            f"{bank_uri}{value}"
            if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/")
            else _rebase_defs_to_bank(value, bank_uri)
        )
        for key, value in node.items()
    }


def _composed_base(
    branch: Any,
    projection: Projection,
    path: str,
    local_prefix: str,
) -> dict[str, Any] | None:
    """Return the projected schema composed by a branch, including hoisted `$defs`."""
    if not isinstance(branch, dict):
        return None
    # `_wrap_ref` has already run on the branch, so a bare reference now looks like
    # `{"allOf": [{"$ref": ...}]}`. Either spelling is composition.
    if set(branch) == {"allOf"} and len(branch["allOf"]) == 1:
        branch = branch["allOf"][0]
    if not isinstance(branch, dict) or set(branch) != {"$ref"}:
        return None
    ref = branch["$ref"]
    block_id = _block_pointer(ref, projection)
    if block_id is not None:
        return project_schema(
            projection.blocks[block_id],
            projection,
            path=path,
            local_prefix=local_prefix,
        )

    defs_prefix = f"{projection.bank_uri}#/$defs/"
    if not ref.startswith(defs_prefix):
        return None
    name = ref[len(defs_prefix) :]
    definitions = [
        schema["$defs"][name]
        for schema in projection.blocks.values()
        if name in schema.get("$defs", {})
    ]
    if not definitions:
        return None
    if any(definition != definitions[0] for definition in definitions[1:]):
        raise ValueError(f"question-bank definition {name!r} is ambiguous")
    projected = project_schema(
        definitions[0],
        projection,
        path=path,
        local_prefix=local_prefix,
    )
    return _rebase_defs_to_bank(projected, projection.bank_uri)

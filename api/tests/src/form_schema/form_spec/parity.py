"""Helpers for proving that a projected form and its hand-written original agree.

Two assertions, and between them they cover everything an applicant can perceive.

**What they read.** The UI schema's `definition` pointers are the enumeration of what a form
renders. So resolve each pointer in both schemas and compare the effective field. Structural
placement then stops mattering by construction -- where a `$defs` sits, whether a reference
is wrapped in `allOf`, which side of a reference a constraint lives on -- because resolving
the pointer collapses all of it. Both steps the renderer takes are taken here first: the
`jsonref` dereference that `form_template_registry` runs at registration, then the `allOf`
merge that `processFormSchema` runs before rendering.

**What they may submit.** Validate a corpus derived from the golden against both schemas and
require identical verdicts. Indifferent to how the schemas are composed, and sensitive to
every difference that could reject an answer.

There is deliberately no assertion about the *shape* of the JSON Schema. Where a constraint
physically lives is one of the choices the specification exists not to inherit, and asserting
it produced two hundred differences that all had to be explained -- which is how a genuine
regression once hid among them.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from src.form_schema.jsonschema_validator import validate_json_schema

# ---------------------------------------------------------------------------
# differences


@dataclasses.dataclass(frozen=True)
class Difference:
    pointer: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind} at {self.pointer}: {self.detail}"


def _brief(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 120 else text[:117] + "..."


def unexplained(differences: list[Difference], allowed: dict[str, str]) -> list[Difference]:
    """Differences with no entry in the allow-list, keyed by `<pointer>#<keyword>`."""
    return [d for d in differences if d.pointer not in allowed]


def unused(differences: list[Difference], allowed: dict[str, str]) -> list[str]:
    """Allow-list entries explaining a difference that is no longer there.

    An explanation for something that has stopped being true is worse than no explanation, so
    a stale entry fails the test that relies on it.
    """
    present = {d.pointer for d in differences}
    return sorted(key for key in allowed if key not in present)


# ---------------------------------------------------------------------------
# what an applicant reads


def pointers(ui_schema: Any) -> list[str]:
    """Every field pointer in a UI schema, in the order the form renders them."""
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        definition = node.get("definition")
        for pointer in definition if isinstance(definition, list) else [definition]:
            if isinstance(pointer, str):
                out.append(pointer)
        for child in node.get("children") or []:
            walk(child)

    walk(ui_schema)
    return out


def _composed(node: dict[str, Any]) -> dict[str, Any]:
    """Collapse a node's `allOf` composition into the node itself.

    The node's own keywords win and branches apply in order, which mirrors the renderer's
    `mergeAllOf` and, more to the point, is what makes a form's label override the label of
    the question it composed. A branch carrying `if` is logic rather than composition and is
    left where it is.
    """
    branches = [b for b in node.get("allOf", []) if isinstance(b, dict) and "if" not in b]
    if not branches:
        return node
    merged: dict[str, Any] = {}
    for source in (*branches, node):
        collapsed = _composed(source) if source is not node else source
        for key, value in collapsed.items():
            if key == "allOf":
                continue
            if key == "properties":
                merged.setdefault("properties", {}).update(value)
            elif key == "required":
                merged["required"] = [*merged.get("required", []), *value]
            else:
                merged[key] = value
    return merged


@dataclasses.dataclass(frozen=True)
class RenderedField:
    schema: dict[str, Any]
    required: bool


def rendered_field(schema: dict[str, Any], pointer: str) -> RenderedField | None:
    """The field a UI pointer addresses, composition resolved. None when unreachable."""
    node = _composed(schema)
    parent: dict[str, Any] = {}
    leaf = ""
    steps = [step for step in pointer.strip("/").split("/") if step]
    index = 0
    while index < len(steps):
        step = steps[index]
        if step == "properties":
            index += 1
            if index >= len(steps):
                return None
            leaf = steps[index]
            parent = node
            child = (node.get("properties") or {}).get(leaf)
            if child is None:
                return None
            node = _composed(child)
        elif step == "items":
            items = node.get("items")
            if not isinstance(items, dict):
                return None
            parent, leaf = {}, ""
            node = _composed(items)
        else:
            return None
        index += 1
    return RenderedField(schema=node, required=leaf in (parent.get("required") or []))


#: Keywords that describe the field itself. `properties` and `required` describe its
#: children, which have their own pointers and are compared there.
_FIELD_KEYWORDS = (
    "type",
    "format",
    "pattern",
    "enum",
    "const",
    "title",
    "description",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "readOnly",
)


def rendered_differences(
    projected: dict[str, Any],
    golden: dict[str, Any],
    ui_schema: Any,
) -> list[Difference]:
    """Compare the two schemas field by field, keyed by what the form renders."""
    out: list[Difference] = []
    for pointer in pointers(ui_schema):
        ours, theirs = rendered_field(projected, pointer), rendered_field(golden, pointer)
        if ours is None or theirs is None:
            out.append(
                Difference(
                    pointer,
                    "unreachable",
                    f"projected={'missing' if ours is None else 'found'}, "
                    f"golden={'missing' if theirs is None else 'found'}",
                )
            )
            continue
        if ours.required != theirs.required:
            out.append(
                Difference(f"{pointer}#required", "field", f"{ours.required} vs {theirs.required}")
            )
        for keyword in _FIELD_KEYWORDS:
            mine, yours = ours.schema.get(keyword), theirs.schema.get(keyword)
            if mine != yours:
                out.append(
                    Difference(
                        f"{pointer}#{keyword}", "field", f"{_brief(mine)} vs {_brief(yours)}"
                    )
                )
    return out


def conditional_branches(schema: dict[str, Any]) -> list[str]:
    """A schema's root conditionals as a sorted set of branches.

    `allOf` is a conjunction, so the order the branches happen to be written in carries no
    meaning: ours follows declaration order and the golden's is arranged by hand.
    """
    import json

    return sorted(
        json.dumps(branch, sort_keys=True)
        for branch in schema.get("allOf", [])
        if isinstance(branch, dict) and "if" in branch
    )


# ---------------------------------------------------------------------------
# what an applicant may submit


def leaf_paths(schema: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Every scalar field in a resolved schema, as a path through the data."""
    out: list[tuple[str, ...]] = []
    merged = _composed(schema)
    properties = merged.get("properties")
    if properties:
        for name, sub in properties.items():
            out.extend(leaf_paths(sub, (*prefix, name)))
        return out
    items = merged.get("items")
    if isinstance(items, dict):
        return out + leaf_paths(items, (*prefix, "[]"))
    if prefix:
        out.append(prefix)
    return out


def _walk(data: Any, path: tuple[str, ...]) -> Any:
    for step in path:
        if data is None:
            return None
        data = data[0] if step == "[]" else data.get(step)
    return data


class _Delete:
    pass


_DELETE = _Delete()


def _mutate(data: Any, path: tuple[str, ...], action: Any) -> Any:
    """A copy of `data` with `action` applied at `path`. `_DELETE` removes the field."""
    out = copy.deepcopy(data)
    node = out
    for step in path[:-1]:
        if node is None:
            return out
        node = node[0] if step == "[]" else node.get(step)
    if node is None:
        return out
    last = path[-1]
    if last == "[]":
        return out
    if action is _DELETE:
        node.pop(last, None)
    else:
        node[last] = action
    return out


def corpus(schema: dict[str, Any], seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seed payloads plus one mutation per field, to exercise every branch of the schema.

    For each leaf: delete it (does requiredness agree?), overrun its `maxLength` and underrun
    its `minLength` (do the limits agree?), and put a value of the wrong type in it (does the
    type agree?). Enumerated fields also get a value outside the enum, which is what catches a
    code list that drifted.
    """
    payloads = list(seeds)
    for seed in seeds:
        for path in leaf_paths(schema):
            if _walk(seed, path) is None:
                continue
            payloads.append(_mutate(seed, path, _DELETE))
            payloads.append(_mutate(seed, path, "x" * 200))
            payloads.append(_mutate(seed, path, ""))
            payloads.append(_mutate(seed, path, 17))
            payloads.append(_mutate(seed, path, "not-a-listed-value"))
    return payloads


def verdicts(schema: dict[str, Any], payload: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (issue.field, issue.type, issue.message) for issue in validate_json_schema(payload, schema)
    }


def behavioral_differences(
    projected: dict[str, Any],
    golden: dict[str, Any],
    payloads: list[dict[str, Any]],
    allowed: dict[tuple[str, str], str] | None = None,
) -> list[str]:
    """Payloads on which the two schemas disagree, with the disagreement spelled out.

    `allowed` names `(field, issue type)` pairs where a difference in verdict is a decision
    rather than a defect, each with a reason. Keep it empty if you can: a difference here is a
    difference an applicant can be stopped by.
    """
    permitted = set(allowed or {})
    out: list[str] = []
    for index, payload in enumerate(payloads):
        ours, theirs = verdicts(projected, payload), verdicts(golden, payload)
        surprising = {
            issue
            for issue in ours ^ theirs
            if (issue[0].removeprefix("$."), issue[1]) not in permitted
        }
        if not surprising:
            continue
        out.append(
            f"payload {index}: only ours {sorted(ours - theirs)}; "
            f"only golden {sorted(theirs - ours)}"
        )
    return out

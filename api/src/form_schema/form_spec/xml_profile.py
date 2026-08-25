"""Project a portable Grants.gov XML profile into the existing XML runtime vocabulary.

The portable artifact addresses canonical camelCase response fields. This adapter applies
Simpler's ordinary legacy-name projection and translates four language-neutral node kinds
into the configuration already consumed by ``XMLGenerationService``. No form names or form
families are known here.
"""

from __future__ import annotations

from typing import Any

from src.form_schema.form_spec.projection import Projection, project_response_pointer, snake_case

PROFILE_CONTRACT = "grants-gov-xml-profile/v1"


def _project_value_declaration(
    declaration: dict[str, Any], projection: Projection, *, path: str
) -> dict[str, Any]:
    """Translate one portable source/constant declaration into runtime vocabulary."""

    has_source = "source" in declaration
    has_constant = "constant" in declaration
    if has_source == has_constant:
        raise ValueError(
            f"portable XML value at {path} must declare exactly one of source or constant"
        )
    projected: dict[str, Any]
    if has_source:
        projected = {"source": _project_source_pointer(declaration["source"], projection)}
    else:
        projected = {"static_value": declaration["constant"]}
    if value_map := declaration.get("valueMap"):
        if not has_source:
            raise ValueError(f"portable XML value map at {path} requires a source")
        projected["value_transform"] = {
            "type": "map_values",
            "params": {"mappings": dict(value_map)},
        }
    return projected


def _project_attributes(
    attributes: dict[str, Any], projection: Projection, *, path: str
) -> dict[str, Any]:
    return {
        name: _project_value_declaration(value, projection, path=f"{path}.@{name}")
        for name, value in attributes.items()
    }


def _project_source_pointer(source: str, projection: Projection) -> str:
    """Project an absolute canonical response pointer into Simpler field names."""

    if not source.startswith("/"):
        raise ValueError(f"Grants.gov XML source must be an absolute JSON pointer: {source!r}")
    return project_response_pointer(source, projection)


def _attachment_children(fields: dict[str, Any], *, path: str) -> dict[str, Any]:
    """Project declared attachment wire fields onto the runtime attachment record."""
    if not fields:
        raise ValueError(f"attachment mapping at {path} has no declared wire fields")
    return {
        snake_case(name): {
            "xml_transform": {
                "target": declaration["element"],
                "namespace": declaration["namespace"],
            }
        }
        for name, declaration in fields.items()
    }


def project_grants_gov_xml_profile(
    profile: dict[str, Any], projection: Projection
) -> dict[str, Any]:
    """Return a runtime transform config without mutating the portable profile."""
    if profile.get("contract") != PROFILE_CONTRACT:
        raise ValueError(f"unsupported Grants.gov XML profile: {profile.get('contract')!r}")

    namespaces = profile.get("namespaces")
    root = profile.get("root")
    xsd = profile.get("xsd")
    mapping = profile.get("mapping")
    attachment = profile.get("attachment", {})
    if (
        not isinstance(namespaces, dict)
        or not isinstance(root, dict)
        or not isinstance(xsd, dict)
        or not isinstance(mapping, dict)
    ):
        raise ValueError("Grants.gov XML profile is missing required objects")

    return {
        "_xml_config": {
            "description": "Projected portable Grants.gov XML profile",
            "version": "1.0",
            "form_name": root["element"],
            "namespaces": dict(namespaces),
            "xsd_url": xsd["uri"],
            "xsd_sha256": xsd["sha256"],
            "xml_structure": {
                "root_element": root["element"],
                "root_namespace_prefix": root["namespacePrefix"],
                "root_attributes": dict(root["attributes"]),
            },
        },
        **_project_fields(
            mapping["fields"],
            projection,
            path="",
            attachment_fields=attachment.get("fields", {}),
        ),
    }


def _project_fields(
    fields: dict[str, Any],
    projection: Projection,
    *,
    path: str,
    attachment_fields: dict[str, Any],
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for canonical_name, node in fields.items():
        canonical_path = f"{path}.{canonical_name}" if path else canonical_name
        source_name = projection.rename(canonical_path, canonical_name)
        projected_node = _project_node(
            node,
            projection,
            path=canonical_path,
            attachment_fields=attachment_fields,
        )
        if node.get("flatten"):
            collisions = set(projected).intersection(projected_node)
            if collisions:
                names = ", ".join(sorted(collisions))
                raise ValueError(
                    f"flattened Grants.gov XML fields collide at {canonical_path}: {names}"
                )
            projected.update(projected_node)
        else:
            projected[source_name] = projected_node
    return projected


def _project_node(
    node: dict[str, Any],
    projection: Projection,
    *,
    path: str,
    attachment_fields: dict[str, Any],
    array_item: bool = False,
    array_item_element: str | None = None,
    array_item_namespace: str | None = None,
) -> dict[str, Any]:
    kind = node["kind"]
    if kind == "value" and node.get("flatten") is True:
        if not array_item:
            raise ValueError(
                f"flattened value mapping is only valid as an array item node at {path}"
            )
        ignored = set(node) - {"kind", "flatten"}
        if ignored:
            names = ", ".join(sorted(ignored))
            raise ValueError(
                f"flattened value mapping cannot declare ignored properties at {path}: {names}"
            )
        if array_item_element is not None:
            item_transform: dict[str, Any] = {"target": array_item_element}
            if array_item_namespace is not None:
                item_transform["namespace"] = array_item_namespace
            return {"xml_transform": item_transform}
        return {"xml_transform": {"flatten_array_item": True}}
    if kind == "attachment" and node.get("flatten") is True:
        if not array_item or array_item_element is None:
            raise ValueError(
                "flattened attachment mapping is only valid as an array item node "
                f"with a declared itemElement at {path}"
            )
        ignored = set(node) - {"kind", "flatten"}
        if ignored:
            names = ", ".join(sorted(ignored))
            raise ValueError(
                f"flattened attachment mapping cannot declare ignored properties at {path}: {names}"
            )
        item_transform = {"target": array_item_element, "type": "attachment"}
        if array_item_namespace is not None:
            item_transform["namespace"] = array_item_namespace
        return {
            "xml_transform": item_transform,
            **_attachment_children(attachment_fields, path=path),
        }
    if node.get("flatten"):
        if kind != "group":
            raise ValueError(f"only group mappings may be flattened at {path}")
        return _project_fields(
            node["fields"],
            projection,
            path=path,
            attachment_fields=attachment_fields,
        )
    runtime_type = {
        "value": None,
        "object": "nested_object",
        "group": "group",
        "array": "array",
        "attachment": "attachment",
    }.get(kind)
    if kind not in {"value", "object", "group", "array", "attachment"}:
        raise ValueError(f"unsupported Grants.gov XML mapping kind at {path}: {kind!r}")

    container = node.get("container")
    if container is not None:
        if kind not in {"value", "attachment"}:
            raise ValueError(f"only value or attachment mappings may use a container at {path}")
        if not isinstance(container, dict):
            raise ValueError(f"container mapping at {path} must be an object")
        element = container.get("element")
        namespace = container.get("namespace")
        if not isinstance(element, str) or not element:
            raise ValueError(f"container mapping at {path} has no element")
        if not isinstance(namespace, str) or not namespace:
            raise ValueError(f"container mapping at {path} has no namespace")

    repeat_element_per_item = node.get("repeatElementPerItem", False)
    if not isinstance(repeat_element_per_item, bool):
        raise ValueError(f"repeatElementPerItem at {path} must be a boolean")
    if repeat_element_per_item and (kind != "array" or not node.get("itemElement")):
        raise ValueError(
            f"repeatElementPerItem at {path} requires an array mapping with itemElement"
        )

    transform: dict[str, Any] = {"target": node["element"]}
    if runtime_type is not None:
        transform["type"] = runtime_type
    if namespace := node.get("namespace"):
        transform["namespace"] = namespace
    if source := node.get("source"):
        transform["source"] = _project_source_pointer(source, projection)
    if "constant" in node:
        if "source" in node:
            raise ValueError(f"portable XML mapping at {path} declares source and constant")
        transform["static_value"] = node["constant"]
    if value_map := node.get("valueMap"):
        transform["value_transform"] = {
            "type": "map_values",
            "params": {"mappings": dict(value_map)},
        }
    if attributes := node.get("attributes"):
        transform["attributes"] = _project_attributes(attributes, projection, path=path)
    if container is not None:
        transform["container"] = {
            "target": container["element"],
            "namespace": container["namespace"],
        }
    if repeat_element_per_item:
        transform["repeat_element_per_item"] = True

    rule: dict[str, Any] = {"xml_transform": transform}
    if kind in {"object", "group"}:
        rule.update(
            _project_fields(
                node["fields"],
                projection,
                path=path,
                attachment_fields=attachment_fields,
            )
        )
    elif kind == "array":
        if item_element := node.get("itemElement"):
            transform["item_wrapper"] = item_element
        if item_namespace := node.get("itemNamespace"):
            transform["item_namespace"] = item_namespace
        if item_attributes := node.get("itemAttributes"):
            transform["item_attributes"] = dict(item_attributes)
        if item_fields := node["items"].get("fields"):
            rule["items"] = _project_fields(
                item_fields,
                projection,
                path=path,
                attachment_fields=attachment_fields,
            )
        else:
            rule["item"] = _project_node(
                node["items"]["node"],
                projection,
                path=f"{path}[*]",
                attachment_fields=attachment_fields,
                array_item=True,
                array_item_element=node.get("itemElement"),
                array_item_namespace=node.get("itemNamespace"),
            )
    elif kind == "attachment":
        rule.update(_attachment_children(attachment_fields, path=path))
    return rule

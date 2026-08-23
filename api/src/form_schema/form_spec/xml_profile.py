"""Project a portable Grants.gov XML profile into the existing XML runtime vocabulary.

The portable artifact addresses canonical camelCase response fields. This adapter applies
Simpler's ordinary legacy-name projection and translates four language-neutral node kinds
into the configuration already consumed by ``XMLGenerationService``. No form names or form
families are known here.
"""

from __future__ import annotations

from typing import Any

from src.form_schema.form_spec.projection import Projection, snake_case

PROFILE_CONTRACT = "grants-gov-xml-profile/v1"


def _project_source_pointer(source: str, projection: Projection) -> str:
    """Project an absolute canonical response pointer into Simpler field names."""

    if not source.startswith("/"):
        raise ValueError(f"Grants.gov XML source must be an absolute JSON pointer: {source!r}")
    canonical_path = ""
    projected: list[str] = []
    for raw_segment in source[1:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        canonical_path = f"{canonical_path}.{segment}" if canonical_path else segment
        projected_segment = projection.rename(canonical_path, segment)
        projected.append(projected_segment.replace("~", "~0").replace("/", "~1"))
    return f"/{'/'.join(projected)}"


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
        projected[source_name] = _project_node(
            node,
            projection,
            path=canonical_path,
            attachment_fields=attachment_fields,
        )
    return projected


def _project_node(
    node: dict[str, Any],
    projection: Projection,
    *,
    path: str,
    attachment_fields: dict[str, Any],
) -> dict[str, Any]:
    kind = node["kind"]
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

    transform: dict[str, Any] = {"target": node["element"]}
    if runtime_type is not None:
        transform["type"] = runtime_type
    if namespace := node.get("namespace"):
        transform["namespace"] = namespace
    if source := node.get("source"):
        transform["source"] = _project_source_pointer(source, projection)

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
            )
    elif kind == "attachment":
        rule.update(_attachment_children(attachment_fields, path=path))
    return rule

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
    runtime_type = {
        "value": None,
        "object": "nested_object",
        "array": "array",
        "attachment": "attachment",
    }.get(kind)
    if kind not in {"value", "object", "array", "attachment"}:
        raise ValueError(f"unsupported Grants.gov XML mapping kind at {path}: {kind!r}")

    transform: dict[str, Any] = {"target": node["element"]}
    if runtime_type is not None:
        transform["type"] = runtime_type
    if namespace := node.get("namespace"):
        transform["namespace"] = namespace

    rule: dict[str, Any] = {"xml_transform": transform}
    if kind == "object":
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
        rule["items"] = _project_fields(
            node["items"]["fields"],
            projection,
            path=path,
            attachment_fields=attachment_fields,
        )
    elif kind == "attachment":
        rule.update(_attachment_children(attachment_fields, path=path))
    return rule

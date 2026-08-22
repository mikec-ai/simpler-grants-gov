import { RJSFSchema } from "@rjsf/utils";
import addFormats from "ajv-formats";
import Ajv2020, { ValidateFunction } from "ajv/dist/2020";
import type { FormValidationWarning } from "src/types/applyForm/types";

export type ConditionalScopeSegment =
  { kind: "property"; name: string } | { kind: "arrayItems" };

export type ConditionalRequiredRule = {
  scope: ConditionalScopeSegment[];
  schemaPointer: string;
  condition: RJSFSchema | boolean;
  thenRequired: string[];
  elseRequired: string[];
  order: number;
};

export type ConditionalRequiredEvaluation = {
  activeRequiredPaths: string[];
  managedPaths: string[];
  warnings: FormValidationWarning[];
};

type ScopeInstance = {
  value: unknown;
  path: string;
};

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validatorCache = new Map<string, ValidateFunction>();

const escapePointer = (value: string): string =>
  value.replaceAll("~", "~0").replaceAll("/", "~1");

const getValidator = (schema: RJSFSchema | boolean): ValidateFunction => {
  const key = JSON.stringify(schema);
  const cached = validatorCache.get(key);
  if (cached) {
    return cached;
  }
  const validator = ajv.compile(schema);
  validatorCache.set(key, validator);
  return validator;
};

const SUPPORTED_PROPERTY_NAME = /^[A-Za-z0-9_]+$/;

const branchRequired = (
  branch: unknown,
  pointer: string,
  branchName: "then" | "else",
): string[] => {
  if (branch === undefined || branch === true) return [];
  if (!branch || typeof branch !== "object" || Array.isArray(branch)) {
    throw new Error(`${pointer}/${branchName} must be a JSON Schema`);
  }
  const branchSchema = branch as Record<string, unknown>;
  const unsupportedKeys = Object.keys(branchSchema).filter(
    (key) => !["required", "title", "description", "$comment"].includes(key),
  );
  if (unsupportedKeys.length > 0) {
    throw new Error(
      `${pointer}/${branchName} contains unsupported effects: ${unsupportedKeys.join(", ")}`,
    );
  }
  if (!Object.hasOwn(branchSchema, "required")) return [];
  const required = branchSchema.required;
  if (
    !Array.isArray(required) ||
    !required.every(
      (item) => typeof item === "string" && SUPPORTED_PROPERTY_NAME.test(item),
    )
  ) {
    throw new Error(
      `${pointer}/${branchName}/required must contain supported property names`,
    );
  }
  return required.map((item: unknown) => String(item));
};

const containsConditional = (value: unknown): boolean => {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.some(containsConditional);
  const record = value as Record<string, unknown>;
  return (
    Object.hasOwn(record, "if") ||
    Object.values(record).some(containsConditional)
  );
};

const resolveLocalRef = (root: RJSFSchema, ref: string): unknown => {
  if (!ref.startsWith("#/")) return undefined;
  return ref
    .slice(2)
    .split("/")
    .map((token) => token.replaceAll("~1", "/").replaceAll("~0", "~"))
    .reduce<unknown>((current, token) => {
      if (!current || typeof current !== "object" || Array.isArray(current)) {
        return undefined;
      }
      return (current as Record<string, unknown>)[token];
    }, root);
};

const validateConditionRefs = (
  condition: unknown,
  root: RJSFSchema,
  pointer: string,
  visitedRefs: ReadonlySet<string> = new Set(),
): void => {
  if (!condition || typeof condition !== "object") return;
  if (Array.isArray(condition)) {
    condition.forEach((item) =>
      validateConditionRefs(item, root, pointer, visitedRefs),
    );
    return;
  }
  const record = condition as Record<string, unknown>;
  if (typeof record.$ref === "string") {
    if (!record.$ref.startsWith("#/$defs/")) {
      throw new Error(
        `${pointer}/if contains an unsupported condition $ref: ${record.$ref}`,
      );
    }
    const referenced = resolveLocalRef(root, record.$ref);
    if (referenced === undefined) {
      throw new Error(
        `${pointer}/if contains an unresolved condition $ref: ${record.$ref}`,
      );
    }
    if (!visitedRefs.has(record.$ref)) {
      validateConditionRefs(
        referenced,
        root,
        pointer,
        new Set([...visitedRefs, record.$ref]),
      );
    }
  }
  Object.values(record).forEach((value) =>
    validateConditionRefs(value, root, pointer, visitedRefs),
  );
};

const conditionWithRootDefinitions = (
  condition: unknown,
  root: RJSFSchema,
): RJSFSchema | boolean =>
  typeof condition === "boolean"
    ? condition
    : {
        ...(root.$schema ? { $schema: root.$schema } : {}),
        ...(root.$defs ? { $defs: root.$defs } : {}),
        ...(condition as Record<string, unknown>),
      };

export const extractConditionalRequiredRules = (
  schema: RJSFSchema,
): ConditionalRequiredRule[] => {
  if (
    schema.$schema &&
    schema.$schema !== "https://json-schema.org/draft/2020-12/schema"
  ) {
    throw new Error(`Unsupported JSON Schema dialect: ${schema.$schema}`);
  }
  const rules: ConditionalRequiredRule[] = [];

  const walk = (
    node: unknown,
    scope: ConditionalScopeSegment[],
    pointer: string,
    resolvingRefs: ReadonlySet<string> = new Set(),
  ): void => {
    if (!node || typeof node !== "object" || Array.isArray(node)) {
      return;
    }
    const schemaNode = node as Record<string, unknown>;
    if (
      typeof schemaNode.$ref === "string" &&
      !resolvingRefs.has(schemaNode.$ref)
    ) {
      const referencedSchema = resolveLocalRef(schema, schemaNode.$ref);
      if (referencedSchema === undefined) {
        throw new Error(
          `${pointer} contains an unresolved $ref: ${schemaNode.$ref}`,
        );
      }
      walk(
        referencedSchema,
        scope,
        schemaNode.$ref,
        new Set([...resolvingRefs, schemaNode.$ref]),
      );
    }
    if (Object.hasOwn(schemaNode, "if")) {
      validateConditionRefs(schemaNode.if, schema, pointer);
      const thenRequired = branchRequired(schemaNode.then, pointer, "then");
      const elseRequired = branchRequired(schemaNode.else, pointer, "else");
      if (thenRequired.length > 0 || elseRequired.length > 0) {
        rules.push({
          scope,
          schemaPointer: pointer,
          condition: conditionWithRootDefinitions(schemaNode.if, schema),
          thenRequired,
          elseRequired,
          order: rules.length,
        });
      }
    }
    ["anyOf", "oneOf", "not", "dependentSchemas", "prefixItems"].forEach(
      (keyword) => {
        if (containsConditional(schemaNode[keyword])) {
          throw new Error(
            `${pointer}/${keyword} contains unsupported conditional requiredness`,
          );
        }
      },
    );
    Object.entries(schemaNode).forEach(([keyword, value]) => {
      if (
        ![
          "$ref",
          "if",
          "then",
          "else",
          "allOf",
          "properties",
          "items",
          "$defs",
          "definitions",
        ].includes(keyword) &&
        containsConditional(value)
      ) {
        throw new Error(
          `${pointer}/${keyword} contains unsupported conditional requiredness`,
        );
      }
    });
    const allOf = schemaNode.allOf;
    if (Array.isArray(allOf)) {
      allOf.forEach((entry, index) => {
        if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
          return;
        }
        walk(entry, scope, `${pointer}/allOf/${index}`, resolvingRefs);
      });
    }

    const properties = schemaNode.properties;
    if (
      properties &&
      typeof properties === "object" &&
      !Array.isArray(properties)
    ) {
      Object.entries(properties).forEach(([name, child]) => {
        if (!SUPPORTED_PROPERTY_NAME.test(name)) {
          throw new Error(
            `${pointer} contains an unsupported property name: ${name}`,
          );
        }
        walk(
          child,
          [...scope, { kind: "property", name }],
          `${pointer}/properties/${escapePointer(name)}`,
          resolvingRefs,
        );
      });
    }
    if (schemaNode.items) {
      walk(
        schemaNode.items,
        [...scope, { kind: "arrayItems" }],
        `${pointer}/items`,
        resolvingRefs,
      );
    }
  };

  walk(schema, [], "#");
  return rules;
};

const expandScope = (
  rootData: object,
  scope: ConditionalScopeSegment[],
): ScopeInstance[] => {
  let instances: ScopeInstance[] = [{ value: rootData, path: "$" }];
  scope.forEach((segment) => {
    const next: ScopeInstance[] = [];
    instances.forEach((instance) => {
      if (segment.kind === "property") {
        if (
          instance.value &&
          typeof instance.value === "object" &&
          !Array.isArray(instance.value) &&
          Object.hasOwn(instance.value, segment.name)
        ) {
          next.push({
            value: (instance.value as Record<string, unknown>)[segment.name],
            path: `${instance.path}.${segment.name}`,
          });
        }
        return;
      }
      if (Array.isArray(instance.value)) {
        instance.value.forEach((value, index) => {
          next.push({ value, path: `${instance.path}[${index}]` });
        });
      }
    });
    instances = next;
  });
  return instances;
};

export const evaluateConditionalRequiredRules = (
  rules: ConditionalRequiredRule[],
  formData: object,
): ConditionalRequiredEvaluation => {
  const activeRequiredPaths = new Set<string>();
  const managedPaths = new Set<string>();
  const warnings: FormValidationWarning[] = [];

  rules
    .toSorted((left, right) => left.order - right.order)
    .forEach((rule) => {
      expandScope(formData, rule.scope).forEach(({ value, path }) => {
        const matches = getValidator(rule.condition)(value);
        const active = matches ? rule.thenRequired : rule.elseRequired;
        [...rule.thenRequired, ...rule.elseRequired].forEach((name) =>
          managedPaths.add(`${path}.${name}`),
        );
        active.forEach((name) => {
          const field = `${path}.${name}`;
          activeRequiredPaths.add(field);
          const isMissing =
            !value ||
            typeof value !== "object" ||
            Array.isArray(value) ||
            !Object.hasOwn(value, name);
          if (isMissing) {
            warnings.push({
              type: "required",
              field,
              message: `'${name}' is a required property`,
              value: null,
            });
          }
        });
      });
    });

  return {
    activeRequiredPaths: [...activeRequiredPaths],
    managedPaths: [...managedPaths],
    warnings,
  };
};

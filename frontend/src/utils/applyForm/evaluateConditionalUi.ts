import type {
  ConditionalUi,
  ConditionalUiPredicate,
  ConditionalUiValueRef,
  ResolvedConditionalUiState,
} from "src/types/applyForm/conditionalUiTypes";
import type { UiSchema } from "src/types/applyForm/types";
import { getByPointer } from "src/utils/formData/formDataUtils";

type EvaluationContext = {
  rootData: object;
  itemStack?: object[];
};

const DEFAULT_STATE: ResolvedConditionalUiState = {
  visible: true,
  interaction: "enabled",
};

const MISSING_VALUE = Symbol("missing conditional UI value");

const resolveRef = (
  ref: ConditionalUiValueRef,
  { rootData, itemStack = [] }: EvaluationContext,
): unknown => {
  const scope =
    ref.scope === "root" ? rootData : itemStack.at(-((ref.ancestor ?? 0) + 1));
  if (!scope) {
    return MISSING_VALUE;
  }
  if (ref.pointer === "") {
    return scope;
  }
  try {
    const value = getByPointer(scope, ref.pointer);
    return value === undefined ? MISSING_VALUE : value;
  } catch {
    return MISSING_VALUE;
  }
};

const isPresent = (value: unknown): boolean =>
  value !== MISSING_VALUE &&
  value !== null &&
  value !== "" &&
  (!Array.isArray(value) || value.length > 0);

export const evaluateConditionalUiPredicate = (
  predicate: ConditionalUiPredicate,
  context: EvaluationContext,
): boolean => {
  switch (predicate.op) {
    case "all":
      return predicate.predicates.every((item) =>
        evaluateConditionalUiPredicate(item, context),
      );
    case "any":
      return predicate.predicates.some((item) =>
        evaluateConditionalUiPredicate(item, context),
      );
    case "not":
      return !evaluateConditionalUiPredicate(predicate.predicate, context);
    case "present":
      return isPresent(resolveRef(predicate.ref, context));
    case "countAtLeast": {
      const value = resolveRef(predicate.ref, context);
      return Array.isArray(value) && value.length >= predicate.minimum;
    }
    case "equals": {
      const value = resolveRef(predicate.ref, context);
      return value !== MISSING_VALUE && value === predicate.value;
    }
    case "notEquals": {
      const value = resolveRef(predicate.ref, context);
      return value !== MISSING_VALUE && value !== predicate.value;
    }
    case "in": {
      const value = resolveRef(predicate.ref, context);
      return (
        value !== MISSING_VALUE &&
        predicate.values.some((candidate) => candidate === value)
      );
    }
  }
};

export const resolveConditionalUiState = (
  conditional: ConditionalUi | undefined,
  context: EvaluationContext,
): ResolvedConditionalUiState => {
  if (!conditional) {
    return DEFAULT_STATE;
  }
  const branch = evaluateConditionalUiPredicate(conditional.when, context)
    ? conditional.then
    : conditional.otherwise;
  return { ...DEFAULT_STATE, ...branch };
};

export const hasConditionalUi = (uiSchema: UiSchema): boolean =>
  uiSchema.some(
    (node) =>
      Boolean(node.conditional) ||
      ("children" in node &&
        Array.isArray(node.children) &&
        hasConditionalUi(node.children as UiSchema)),
  );

export const filterVisibleUiSchema = (
  uiSchema: UiSchema,
  rootData: object,
): UiSchema =>
  uiSchema.reduce<UiSchema>((visibleNodes, node) => {
    const state = resolveConditionalUiState(node.conditional, { rootData });
    if (!state.visible) return visibleNodes;
    if (node.type === "section") {
      visibleNodes.push({
        ...node,
        children: filterVisibleUiSchema(node.children, rootData),
      });
      return visibleNodes;
    }
    visibleNodes.push(node);
    return visibleNodes;
  }, []);

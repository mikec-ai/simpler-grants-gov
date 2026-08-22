export type ConditionalUiScalar = string | number | boolean | null;

export type ConditionalUiValueRef = {
  scope: "root" | "item";
  pointer: string;
  ancestor?: number;
};

export type ConditionalUiPredicate =
  | {
      op: "equals" | "notEquals";
      ref: ConditionalUiValueRef;
      value: ConditionalUiScalar;
    }
  | {
      op: "in";
      ref: ConditionalUiValueRef;
      values: ConditionalUiScalar[];
    }
  | {
      op: "present";
      ref: ConditionalUiValueRef;
    }
  | {
      op: "all" | "any";
      predicates: ConditionalUiPredicate[];
    }
  | {
      op: "not";
      predicate: ConditionalUiPredicate;
    };

export type ConditionalUiState = {
  visible?: boolean;
  interaction?: "enabled" | "disabled" | "readOnly";
};

export type ConditionalUi = {
  when: ConditionalUiPredicate;
  then: ConditionalUiState;
  otherwise?: ConditionalUiState;
};

export type ResolvedConditionalUiState = {
  visible: boolean;
  interaction: "enabled" | "disabled" | "readOnly";
};

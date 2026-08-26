"use client";

import { FormContextType, RJSFSchema, StrictRJSFSchema } from "@rjsf/utils";
import { UswdsWidgetProps } from "src/types/applyForm/types";

import { useEffect, useRef, useState } from "react";
import { Checkbox, FormGroup } from "@trussworks/react-uswds";

import { FieldErrors } from "src/components/core/forms/FieldErrors";

type Choice = { code: string; label: string };
type Combination = { value: string; members: string[] };
type EncodedCheckboxGroup = {
  choices: Choice[];
  combinations: Combination[];
};

function readContract(schema: RJSFSchema): EncodedCheckboxGroup {
  const contract = (schema as Record<string, unknown>)[
    "x-encoded-checkbox-group"
  ];
  if (!contract || typeof contract !== "object" || Array.isArray(contract)) {
    throw new Error("EncodedCheckboxGroup requires x-encoded-checkbox-group");
  }

  const contractRecord = contract as Record<string, unknown>;
  if (Object.keys(contractRecord).sort().join(",") !== "choices,combinations") {
    throw new Error(
      "EncodedCheckboxGroup contract requires exactly choices and combinations",
    );
  }
  const { choices, combinations } = contractRecord;
  if (!Array.isArray(choices) || !Array.isArray(combinations)) {
    throw new Error("EncodedCheckboxGroup requires choices and combinations");
  }
  if (
    choices.length === 0 ||
    choices.some((choice: unknown) => {
      if (!choice || typeof choice !== "object" || Array.isArray(choice)) {
        return true;
      }
      const record = choice as Record<string, unknown>;
      return (
        Object.keys(record).sort().join(",") !== "code,label" ||
        typeof record.code !== "string" ||
        !record.code ||
        typeof record.label !== "string" ||
        !record.label
      );
    })
  ) {
    throw new Error(
      "EncodedCheckboxGroup choices must have unique code and label strings",
    );
  }
  const typedChoices = choices as Choice[];
  const codes = typedChoices.map(({ code }) => code);
  const labels = typedChoices.map(({ label }) => label);
  if (
    new Set(codes).size !== codes.length ||
    new Set(labels).size !== labels.length
  ) {
    throw new Error(
      "EncodedCheckboxGroup choice codes and labels must be unique",
    );
  }

  const typedCombinations = combinations as Combination[];
  const enumValues = Array.isArray(schema.enum)
    ? schema.enum.filter((value): value is string => typeof value === "string")
    : [];
  if (enumValues.length !== schema.enum?.length) {
    throw new Error("EncodedCheckboxGroup schema enum values must be strings");
  }
  const seenValues = new Set<string>();
  for (const combination of typedCombinations) {
    if (
      !combination ||
      typeof combination !== "object" ||
      Array.isArray(combination) ||
      Object.keys(combination).sort().join(",") !== "members,value" ||
      typeof combination.value !== "string" ||
      !combination.value ||
      !Array.isArray(combination.members) ||
      combination.members.length === 0 ||
      combination.members.some((member) => !codes.includes(member)) ||
      new Set(combination.members).size !== combination.members.length ||
      seenValues.has(combination.value)
    ) {
      throw new Error("EncodedCheckboxGroup combinations are invalid");
    }
    seenValues.add(combination.value);
  }
  if (
    enumValues.length !== seenValues.size ||
    enumValues.some((value) => !seenValues.has(value))
  ) {
    throw new Error(
      "EncodedCheckboxGroup combinations must exactly match schema enum values",
    );
  }

  return { choices: typedChoices, combinations: typedCombinations };
}

export default function EncodedCheckboxGroupWidget<
  T = unknown,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = never,
>({
  id,
  disabled,
  readOnly,
  required,
  schema,
  value,
  rawErrors = [],
  autofocus = false,
  formContext,
  onChange = () => ({}),
  onBlur = () => ({}),
  onFocus = () => ({}),
}: UswdsWidgetProps<T, S, F>) {
  const contract = readContract(schema);
  const externalValue = typeof value === "string" ? value : "";
  const [encodedValue, setEncodedValue] = useState(externalValue);
  const hiddenInputRef = useRef<HTMLInputElement>(null);
  const syncFormData = formContext?.widgetSupport?.syncFormData;
  const externalValueRef = useRef(externalValue);
  useEffect(() => {
    if (externalValueRef.current === externalValue) return;
    externalValueRef.current = externalValue;
    setEncodedValue(externalValue);
  }, [externalValue]);
  const selected =
    contract.combinations.find(
      (combination) => combination.value === encodedValue,
    )?.members ?? [];
  const error = rawErrors.length ? true : undefined;
  const describedBy = [
    schema.description ? `${id}__description` : undefined,
    error ? `error-for-${id}` : undefined,
  ]
    .filter(Boolean)
    .join(" ");

  const toggle = (code: string): void => {
    const nextMembers = selected.includes(code)
      ? selected.filter((member) => member !== code)
      : [...selected, code];
    const next = contract.combinations.find(
      (combination) =>
        combination.members.length === nextMembers.length &&
        combination.members.every((member) => nextMembers.includes(member)),
    );
    const nextValue = next?.value ?? "";
    if (hiddenInputRef.current) hiddenInputRef.current.value = nextValue;
    setEncodedValue(nextValue);
    onChange(nextValue);
    // Apply forms derive conditional state from native FormData. Synchronize the
    // encoded hidden value before the bubbling checkbox event can rerender this
    // conditional subtree and remount the widget with its previous value.
    syncFormData?.();
  };

  const canToggle = (code: string): boolean => {
    if (selected.includes(code)) return true;
    const nextMembers = [...selected, code];
    return contract.combinations.some(
      (combination) =>
        combination.members.length === nextMembers.length &&
        combination.members.every((member) => nextMembers.includes(member)),
    );
  };

  return (
    <FormGroup error={error}>
      <fieldset className="usa-fieldset">
        <legend className="usa-legend">
          {schema.title}
          {required && <span className="usa-hint usa-hint--required"> *</span>}
        </legend>
        {schema.description && (
          <div id={`${id}__description`} className="usa-hint">
            {schema.description}
          </div>
        )}
        {error && (
          <FieldErrors fieldName={id} rawErrors={rawErrors as string[]} />
        )}
        <input
          ref={hiddenInputRef}
          type="hidden"
          name={id}
          value={encodedValue}
          readOnly
        />
        {contract.choices.map((choice, index) => (
          <Checkbox
            key={choice.code}
            id={`${id}__${index}`}
            name=""
            label={choice.label}
            checked={selected.includes(choice.code)}
            disabled={disabled || readOnly || !canToggle(choice.code)}
            autoFocus={autofocus && index === 0}
            aria-describedby={describedBy || undefined}
            onChange={() => toggle(choice.code)}
            onBlur={() => onBlur(id, encodedValue)}
            onFocus={() => onFocus(id, encodedValue)}
          />
        ))}
      </fieldset>
    </FormGroup>
  );
}

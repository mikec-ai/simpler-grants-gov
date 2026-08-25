import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import React from "react";

import MultiSelectWidget from "src/components/apply-form/widgets/MultiSelectWidget";

jest.mock("@trussworks/react-uswds", () => {
  const actual = jest.requireActual<typeof import("@trussworks/react-uswds")>(
    "@trussworks/react-uswds",
  );
  return {
    ...actual,
    ComboBox: React.forwardRef(function MockComboBox(
      {
        options,
        onChange,
        disabled,
      }: {
        options: { value: string | number; label: string }[];
        onChange: (value?: string) => void;
        disabled?: boolean;
      },
      ref: React.ForwardedRef<{ clearSelection: () => void }>,
    ) {
      React.useImperativeHandle(ref, () => ({
        clearSelection: () => undefined,
      }));
      return (
        <select
          aria-label="choices"
          disabled={disabled}
          defaultValue=""
          onChange={(event) => onChange(event.currentTarget.value)}
        >
          <option value="">Choose</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    }),
  };
});

const options = {
  enumOptions: [
    { value: "Asian", label: "Asian" },
    { value: "White", label: "White" },
    { value: "Do Not Wish to Provide", label: "Do Not Wish to Provide" },
  ],
  exclusiveValues: ["Do Not Wish to Provide"],
};

describe("MultiSelectWidget", () => {
  it("replaces other choices when an exclusive value is selected and vice versa", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    render(
      <MultiSelectWidget
        id="race"
        schema={{ type: "array", title: "Race", maxItems: 5 }}
        value={["Asian"]}
        options={options}
        onChange={onChange}
      />,
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: "choices" }),
      "Do Not Wish to Provide",
    );
    expect(onChange).toHaveBeenLastCalledWith(["Do Not Wish to Provide"]);

    await user.selectOptions(
      screen.getByRole("combobox", { name: "choices" }),
      "White",
    );
    expect(onChange).toHaveBeenLastCalledWith(["White"]);
  });

  it("preserves non-string enum values when synchronizing ordinary selections", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    render(
      <MultiSelectWidget
        id="numbers"
        schema={{ type: "array", title: "Numbers" }}
        value={[]}
        options={{
          enumOptions: [
            { value: 1, label: "One" },
            { value: 2, label: "Two" },
          ],
        }}
        onChange={onChange}
      />,
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: "choices" }),
      "2",
    );

    expect(onChange).toHaveBeenLastCalledWith([2]);
  });
});

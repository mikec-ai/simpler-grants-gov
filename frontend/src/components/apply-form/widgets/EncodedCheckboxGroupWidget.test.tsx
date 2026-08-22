import { RJSFSchema } from "@rjsf/utils";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UswdsWidgetProps } from "src/types/applyForm/types";

import EncodedCheckboxGroupWidget from "src/components/apply-form/widgets/EncodedCheckboxGroupWidget";

const schema: RJSFSchema = {
  type: "string",
  title: "Revision type",
  enum: ["A", "B", "C", "D", "E", "AC", "AD", "BC", "BD"],
  "x-encoded-checkbox-group": {
    choices: [
      { code: "A", label: "A. Increase Award" },
      { code: "B", label: "B. Decrease Award" },
      { code: "C", label: "C. Increase Duration" },
      { code: "D", label: "D. Decrease Duration" },
      { code: "E", label: "E. Other" },
    ],
    combinations: ["A", "B", "C", "D", "E", "AC", "AD", "BC", "BD"].map(
      (value) => ({ value, members: [...value] }),
    ),
  },
};

const props = {
  id: "application_type--revision_code",
  schema,
  value: "A",
  required: true,
  disabled: false,
  readOnly: false,
  rawErrors: [],
  options: {},
  onChange: jest.fn(),
  onBlur: jest.fn(),
  onFocus: jest.fn(),
} as unknown as UswdsWidgetProps;

describe("EncodedCheckboxGroupWidget", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders choices while submitting only the encoded wire value", () => {
    render(
      <form data-testid="revision-form">
        <EncodedCheckboxGroupWidget {...props} />
      </form>,
    );

    expect(
      screen.getByRole("checkbox", { name: "A. Increase Award" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "C. Increase Duration" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("checkbox", { name: "B. Decrease Award" }),
    ).toBeDisabled();
    expect([
      ...new FormData(
        screen.getByTestId<HTMLFormElement>("revision-form"),
      ).entries(),
    ]).toEqual([["application_type--revision_code", "A"]]);
  });

  it("encodes only a source-approved combination", async () => {
    const user = userEvent.setup();
    render(<EncodedCheckboxGroupWidget {...props} />);

    await user.click(
      screen.getByRole("checkbox", { name: "C. Increase Duration" }),
    );
    expect(props.onChange).toHaveBeenCalledWith("AC");
  });

  it("fails closed when the contract does not match the schema enum", () => {
    expect(() =>
      render(
        <EncodedCheckboxGroupWidget
          {...props}
          schema={{ ...schema, enum: [...(schema.enum ?? []), "AB"] }}
        />,
      ),
    ).toThrow("combinations must exactly match schema enum values");
  });
});

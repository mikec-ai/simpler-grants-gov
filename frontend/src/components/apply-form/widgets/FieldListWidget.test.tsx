/* eslint-disable testing-library/no-node-access -- parses vendored JSON artifacts, not DOM nodes */
import fs from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import FieldListWidget from "src/components/apply-form/widgets/FieldListWidget";

jest.mock("src/components/apply-form/widgets/WidgetRenderers", () => ({
  renderWidget: jest.fn(
    ({
      props,
    }: {
      props: {
        id: string;
        value?: unknown;
        rawErrors?: string[];
        additionalDescribedById?: string;
        disabled?: boolean;
        readOnly?: boolean;
        onChange?: (value: unknown) => void;
      };
    }) => {
      const displayValue =
        typeof props.value === "string" ||
        typeof props.value === "number" ||
        typeof props.value === "boolean"
          ? String(props.value)
          : "";

      return (
        <div>
          <input
            data-testid="mock-widget"
            data-widget-id={props.id}
            data-entry-description-id={props.additionalDescribedById}
            data-disabled={String(Boolean(props.disabled))}
            data-read-only={String(Boolean(props.readOnly))}
            aria-label={props.id}
            value={displayValue}
            onChange={(event) => props.onChange?.(event.target.value)}
          />
          {props.rawErrors?.map((error) => (
            <p key={error}>{error}</p>
          ))}
        </div>
      );
    },
  ),
}));

const baseGroupDefinition = [
  {
    widget: "Text" as const,
    baseId: "contacts[~~index~~]--first_name",
    definition: "/properties/contact_people_test/items/properties/first_name",
    storagePath: ["first_name"],
    generalProps: {
      schema: { type: "string", title: "First Name" },
      rawErrors: [],
      options: {},
    },
  },
];

const nestedGroupDefinition = [
  {
    widget: "Text" as const,
    baseId: "contacts[~~index~~]--address--street1",
    definition:
      "/properties/contact_people_test/items/properties/address/properties/street1",
    storagePath: ["address", "street1"],
    generalProps: {
      schema: { type: "string", title: "Street 1" },
      rawErrors: [],
      options: {},
    },
  },
];

const recursiveGroupDefinition = [
  {
    widget: "FieldList" as const,
    baseId: "contacts[~~index~~]--periods",
    definition: "/properties/contacts/items/properties/periods",
    storagePath: ["periods"],
    generalProps: {
      schema: { type: "array" as const, title: "Periods" },
      label: "Periods",
      minItems: 1,
      groupDefinition: [
        {
          widget: "Text" as const,
          baseId: "periods[~~index~~]--amount",
          definition:
            "/properties/contacts/items/properties/periods/items/properties/amount",
          storagePath: ["amount"],
          generalProps: {
            schema: { type: "string", title: "Amount" },
            rawErrors: [],
            options: {},
          },
        },
      ],
    },
  },
];

const keyPersonSchema = JSON.parse(
  fs.readFileSync(
    path.resolve(
      process.cwd(),
      "../api/src/form_schema/form_spec/artifacts/forms/rr-key-person-expanded/schema.json",
    ),
    "utf8",
  ),
) as {
  properties: {
    seniorKeyPersons: { title: string; maxItems: number };
  };
};

const keyPersonUiSchema = JSON.parse(
  fs.readFileSync(
    path.resolve(
      process.cwd(),
      "../api/src/form_schema/form_spec/artifacts/forms/rr-key-person-expanded/sgg/ui-schema.json",
    ),
    "utf8",
  ),
) as Array<{
  children?: Array<{ type: string; name?: string; label?: string }>;
}>;

const keyPersonFieldList = keyPersonUiSchema
  .flatMap((node) => node.children ?? [])
  .find(
    (node) => node.type === "fieldList" && node.name === "seniorKeyPersons",
  );

describe("FieldListWidget", () => {
  it("uses fully qualified keys when nested fields share a leaf name", () => {
    const consoleError = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    render(
      <FieldListWidget
        id="budget_year"
        key="budget_year"
        schema={{ type: "array", title: "Budget period" }}
        label="Budget period"
        minItems={1}
        groupDefinition={[
          {
            ...baseGroupDefinition[0],
            baseId: "budget_year[~~index~~]--key_person--requested_salary",
            storagePath: ["key_person", "requested_salary"],
          },
          {
            ...baseGroupDefinition[0],
            baseId: "budget_year[~~index~~]--other_personnel--requested_salary",
            storagePath: ["other_personnel", "requested_salary"],
          },
        ]}
        rawErrors={[]}
        requiredFields={[]}
        name="budget_year"
      />,
    );

    expect(screen.getAllByTestId("mock-widget")).toHaveLength(2);
    expect(
      consoleError.mock.calls.some((call) =>
        String(call[0]).includes("same key"),
      ),
    ).toBe(false);
    consoleError.mockRestore();
  });

  it("uses the R&R Key Person artifact for add, delete, and maximum interactions", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    const field = keyPersonSchema.properties.seniorKeyPersons;

    expect(keyPersonFieldList?.label).toBe(field.title);
    const { rerender } = render(
      <FieldListWidget
        key="key-person-interactions"
        id="seniorKeyPersons"
        schema={{ type: "array", title: field.title }}
        label={keyPersonFieldList?.label ?? field.title}
        maxItems={field.maxItems}
        value={[{ first_name: "Casey" }]}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="seniorKeyPersons"
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: /addEntry/i }));
    expect(onChange).toHaveBeenLastCalledWith([{ first_name: "Casey" }, {}]);
    await user.click(
      screen.getAllByRole("button", { name: /deleteEntry/i })[1],
    );
    expect(onChange).toHaveBeenLastCalledWith([{ first_name: "Casey" }]);

    rerender(
      <FieldListWidget
        key="key-person-at-maximum"
        id="seniorKeyPersons"
        schema={{ type: "array", title: field.title }}
        label={keyPersonFieldList?.label ?? field.title}
        maxItems={field.maxItems}
        value={Array.from({ length: field.maxItems }, () => ({}))}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="seniorKeyPersons"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole("button", { name: /addEntry/i })).toBeDisabled();
  });

  it("requires a valid current row before adding when configured", async () => {
    const user = userEvent.setup();
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        validateBeforeAdd={true}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={["contact_people_test/first_name"]}
        name="contacts"
      />,
    );

    const add = screen.getByRole("button", { name: /addEntry/i });
    expect(add).toBeDisabled();
    await user.type(screen.getByTestId("mock-widget"), "Ada");
    expect(add).toBeEnabled();
  });

  it("evaluates item-scoped interaction conditions independently for each row", () => {
    const conditionalGroupDefinition = [
      {
        ...nestedGroupDefinition[0],
        conditional: {
          when: {
            op: "equals" as const,
            ref: { scope: "item" as const, pointer: "/address/country" },
            value: "USA: UNITED STATES",
          },
          then: { interaction: "enabled" as const },
          otherwise: { interaction: "disabled" as const },
        },
        generalProps: {
          ...nestedGroupDefinition[0].generalProps,
          formContext: { rootFormData: {} },
        },
      },
    ];

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        groupDefinition={conditionalGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        value={[
          { address: { country: "USA: UNITED STATES", street1: "One" } },
          { address: { country: "CAN: CANADA", street1: "Two" } },
        ]}
      />,
    );

    const fields = screen.getAllByTestId("mock-widget");
    expect(fields[0]).toHaveAttribute("data-disabled", "false");
    expect(fields[1]).toHaveAttribute("data-disabled", "true");
  });

  it("renders label, description, and minimum entry widgets", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        description="Add contacts"
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Contacts" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Add contacts")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /contacts\s+1/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("mock-widget")).toHaveLength(1);
  });

  it("does not render the FieldList heading when hideFieldListHeading is true", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        hideFieldListHeading={true}
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    // The top FieldList heading is omitted when hiding is enabled.
    expect(
      screen.queryByRole("heading", { name: "Contacts", level: 3 }),
    ).not.toBeInTheDocument();
    // Each repeatable list item keeps its visible numbered heading.
    expect(
      screen.getByRole("heading", { name: /contacts\s+1/i }),
    ).toBeInTheDocument();
  });

  it("keeps the FieldList heading visible when hideFieldListHeading is false", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        hideFieldListHeading={false}
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    const fieldListHeading = screen.getByRole("heading", {
      name: "Contacts",
      level: 3,
    });

    // With hiding disabled, the heading should remain visually available.
    expect(fieldListHeading).not.toHaveClass("usa-sr-only");
  });

  it("provides the FieldList label through the container aria-label", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        hideFieldListHeading={true}
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(screen.getByLabelText("Contacts")).toBeInTheDocument();
  });

  it("renders no entries when minItems is 0", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={0}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(
      screen.queryByRole("heading", { name: /contacts\s+1/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("mock-widget")).toHaveLength(0);
  });

  it("renders no entries when minItems is undefined", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(
      screen.queryByRole("heading", { name: /contacts\s+1/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("mock-widget")).toHaveLength(0);
  });

  it("renders minItems number of entries", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={2}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(
      screen.getByRole("heading", { name: /contacts\s+1/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /contacts\s+2/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("mock-widget")).toHaveLength(2);
  });

  it("adds a row", async () => {
    const user = userEvent.setup();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    await user.click(screen.getByRole("button", { name: /addEntry/i }));

    expect(
      screen.getByRole("heading", { name: /contacts\s+2/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("mock-widget")).toHaveLength(2);
  });

  it("disables add when maxItems is reached", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        maxItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(screen.getByRole("button", { name: /addEntry/i })).toBeDisabled();
  });

  it("locks repeated entries, including add, edit, and delete controls", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        value={[{ first_name: "One" }, { first_name: "Two" }]}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        isFormLocked={true}
      />,
    );

    expect(screen.getByRole("button", { name: /addEntry/i })).toBeDisabled();
    screen
      .getAllByRole("button", { name: /deleteEntry/i })
      .forEach((button) => {
        expect(button).toBeDisabled();
      });
    screen.getAllByTestId("mock-widget").forEach((field) => {
      expect(field).toHaveAttribute("data-disabled", "true");
    });
  });

  it("removes a row without going below minItems", async () => {
    const user = userEvent.setup();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        value={[{}, {}]}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    const deleteButtons = screen.getAllByRole("button", {
      name: /deleteEntry/i,
    });

    await user.click(deleteButtons[0]);

    expect(
      screen.queryByRole("heading", { name: /contacts\s+2/i }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByTestId("mock-widget")).toHaveLength(1);
  });

  it("disables delete when minItems is reached", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(
      screen.getByRole("button", { name: /deleteEntry Contacts 1/i }),
    ).toBeDisabled();
  });

  it("renders FieldList child errors inline", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[
          {
            type: "required",
            field: "$.contacts[0].first_name",
            message: "first_name is required",
            value: null,
            formatted: "First Name is required",
            definition:
              "/properties/contact_people_test/items/properties/first_name",
            htmlField: "contacts[0]--first_name",
          },
        ]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(screen.getByText("First Name is required")).toBeInTheDocument();
  });

  it("passes the FieldList entry heading id to child widgets", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    const entryHeading = screen.getByRole("heading", {
      name: /contacts\s+1/i,
    });

    expect(screen.getByTestId("mock-widget")).toHaveAttribute(
      "data-entry-description-id",
      entryHeading.id,
    );
  });

  it("preserves child schema protection when rendering a FieldList entry", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        groupDefinition={[
          {
            ...baseGroupDefinition[0],
            generalProps: {
              ...baseGroupDefinition[0].generalProps,
              disabled: true,
              readOnly: true,
            },
          },
        ]}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(screen.getByTestId("mock-widget")).toHaveAttribute(
      "data-disabled",
      "true",
    );
    expect(screen.getByTestId("mock-widget")).toHaveAttribute(
      "data-read-only",
      "true",
    );
  });

  it("renders nested FieldList values from storagePath", () => {
    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        value={[{ address: { street1: "123 Main" } }]}
        groupDefinition={nestedGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    expect(screen.getByLabelText("contacts[0]--address--street1")).toHaveValue(
      "123 Main",
    );
  });

  it("updates nested FieldList values using storagePath", async () => {
    const user = userEvent.setup();
    const onChangeMock = jest.fn();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        value={[{}]}
        groupDefinition={nestedGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        onChange={onChangeMock}
      />,
    );

    await user.type(
      screen.getByLabelText("contacts[0]--address--street1"),
      "123 Main",
    );

    expect(onChangeMock).toHaveBeenLastCalledWith([
      { address: { street1: "123 Main" } },
    ]);
  });

  it("renders and updates a recursively nested FieldList", async () => {
    const user = userEvent.setup();
    const onChangeMock = jest.fn();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        value={[{ periods: [{ amount: "10" }] }]}
        groupDefinition={recursiveGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        onChange={onChangeMock}
      />,
    );

    const amount = screen.getByLabelText("contacts[0]--periods[0]--amount");
    expect(amount).toHaveValue("10");
    await user.clear(amount);
    await user.type(amount, "25");

    expect(onChangeMock).toHaveBeenLastCalledWith([
      { periods: [{ amount: "25" }] },
    ]);
  });

  it("marks the form dirty when a FieldList child field changes", async () => {
    const user = userEvent.setup();
    const markFormDirtyMock = jest.fn();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        formContext={{
          widgetSupport: {
            markFormDirty: markFormDirtyMock,
          },
        }}
      />,
    );

    await user.type(screen.getByLabelText("contacts[0]--first_name"), "Jane");

    expect(markFormDirtyMock).toHaveBeenCalled();
  });

  it("marks the form dirty when a FieldList row is added", async () => {
    const user = userEvent.setup();
    const markFormDirtyMock = jest.fn();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        formContext={{
          widgetSupport: {
            markFormDirty: markFormDirtyMock,
          },
        }}
      />,
    );

    await user.click(screen.getByRole("button", { name: /addEntry/i }));

    expect(markFormDirtyMock).toHaveBeenCalledTimes(1);
  });

  it("preserves unsaved entry values when deleting another entry", async () => {
    const user = userEvent.setup();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={2}
        maxItems={3}
        value={[{ first_name: "One" }, { first_name: "Two" }]}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
      />,
    );

    await user.click(screen.getByRole("button", { name: /addEntry/i }));
    await user.type(screen.getByLabelText("contacts[2]--first_name"), "Three");

    const deleteButtons = screen.getAllByRole("button", {
      name: /deleteEntry/i,
    });

    await user.click(deleteButtons[1]);

    expect(screen.getByLabelText("contacts[1]--first_name")).toHaveValue(
      "Three",
    );
  });

  it("marks the form dirty when a FieldList row is deleted", async () => {
    const user = userEvent.setup();
    const markFormDirtyMock = jest.fn();

    render(
      <FieldListWidget
        id="contacts"
        key="contacts"
        schema={{ type: "array", title: "Contacts" }}
        label="Contacts"
        minItems={1}
        value={[{}, {}]}
        groupDefinition={baseGroupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="contacts"
        formContext={{
          widgetSupport: {
            markFormDirty: markFormDirtyMock,
          },
        }}
      />,
    );

    const deleteButtons = screen.getAllByRole("button", {
      name: /deleteEntry/i,
    });

    await user.click(deleteButtons[0]);

    expect(markFormDirtyMock).toHaveBeenCalledTimes(1);
  });
});

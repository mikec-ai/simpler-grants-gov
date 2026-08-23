/* eslint-disable testing-library/no-node-access -- parses vendored JSON artifacts, not DOM nodes */
import fs from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import FieldListWidget from "src/components/apply-form/widgets/FieldListWidget";
import { FieldListGroupItem, UiSchema } from "src/types/applyForm/types";
import { Attachment } from "src/types/attachmentTypes";
import { addPrintWidgetToFields } from "src/utils/applyForm/applyFormUtils";

const mockAttachments: Attachment[] = [
  {
    application_attachment_id: "bio-id",
    file_name: "casey-biographical-sketch.pdf",
    download_path: "/download/bio-id",
    file_size_bytes: 100,
    mime_type: "application/pdf",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
  {
    application_attachment_id: "support-id",
    file_name: "casey-current-support.pdf",
    download_path: "/download/support-id",
    file_size_bytes: 100,
    mime_type: "application/pdf",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
];

jest.mock("src/hooks/ApplicationAttachments", () => ({
  useApplicationAttachments: () => ({ attachments: mockAttachments }),
}));

const artifactPath = path.resolve(
  process.cwd(),
  "../api/src/form_schema/form_spec/artifacts/forms/rr-key-person-expanded/sgg/ui-schema.json",
);

describe("R&R Senior/Key Person print canary", () => {
  it("preserves the repeated-person structure and prints its nested attachments", () => {
    const uiSchema = JSON.parse(
      fs.readFileSync(artifactPath, "utf8"),
    ) as UiSchema;
    const printSchema = addPrintWidgetToFields(uiSchema);
    const repeatedPeople = printSchema
      .flatMap((node) => (node.type === "section" ? node.children : [node]))
      .find((node) => node.type === "fieldList");

    expect(repeatedPeople?.type).toBe("fieldList");
    if (repeatedPeople?.type !== "fieldList") {
      throw new Error(
        "R&R Senior/Key Person has no repeated-person field list",
      );
    }

    expect(repeatedPeople.children).toHaveLength(27);
    expect(
      repeatedPeople.children
        .filter(
          (child) =>
            child.type === "field" && child.widget === "PrintAttachment",
        )
        .map((child) => child.definition),
    ).toEqual([
      "/properties/seniorKeyPersons/items/properties/biographicalSketch",
      "/properties/seniorKeyPersons/items/properties/currentPendingSupport",
    ]);
    expect(
      repeatedPeople.children.filter(
        (child) => child.type === "field" && child.widget === "Print",
      ),
    ).toHaveLength(25);

    const printedFields = repeatedPeople.children.filter(
      (child) =>
        child.type === "field" &&
        [
          "/properties/seniorKeyPersons/items/properties/name/properties/firstName",
          "/properties/seniorKeyPersons/items/properties/biographicalSketch",
          "/properties/seniorKeyPersons/items/properties/currentPendingSupport",
        ].includes(String(child.definition)),
    );
    const groupDefinition = printedFields.map((child) => {
      if (child.type !== "field") throw new Error("Expected field");
      const definition = String(child.definition);
      const definitionParts = definition.split("/");
      const propertyName = definitionParts[definitionParts.length - 1] ?? "";
      const storagePath: string[] = definition.includes("/name/properties/")
        ? ["name", propertyName]
        : [propertyName];
      const titles: Record<string, string> = {
        firstName: "First Name",
        biographicalSketch: "Biographical Sketch",
        currentPendingSupport: "Current and Pending Support",
      };
      return {
        widget: child.widget ?? "Print",
        baseId: `seniorKeyPersons[~~index~~]--${propertyName}`,
        definition,
        storagePath,
        generalProps: {
          schema: { type: "string", title: titles[propertyName] },
          rawErrors: [],
          options: {},
        },
      } as FieldListGroupItem;
    });

    render(
      <FieldListWidget
        key="key-person-print"
        id="seniorKeyPersons"
        schema={{ type: "array", title: "Senior / Key Person" }}
        label="Senior / Key Person"
        groupDefinition={groupDefinition}
        rawErrors={[]}
        requiredFields={[]}
        name="seniorKeyPersons"
        value={[
          {
            name: { firstName: "Casey" },
            biographicalSketch: "bio-id",
            currentPendingSupport: "support-id",
          },
        ]}
        isFormLocked={true}
      />,
    );

    expect(screen.getByText("Casey")).toBeInTheDocument();
    expect(
      screen.getByText("casey-biographical-sketch.pdf"),
    ).toBeInTheDocument();
    expect(screen.getByText("casey-current-support.pdf")).toBeInTheDocument();
  });
});

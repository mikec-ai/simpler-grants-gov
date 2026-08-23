import fs from "node:fs";
import path from "node:path";
import { UiSchema } from "src/types/applyForm/types";
import { addPrintWidgetToFields } from "src/utils/applyForm/applyFormUtils";

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
  });
});

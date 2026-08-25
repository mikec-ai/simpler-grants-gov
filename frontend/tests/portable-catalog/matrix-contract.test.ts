import fs from "fs";
import os from "os";
import path from "path";
import {
  assertPortableMatrixEnvironment,
  classifyBoundary,
  completeBlockedProbes,
  firstAddressableAttachmentDefinition,
  loadBrowserPlan,
  observedBoundary,
  PLAN_CONTRACT,
  RECEIPT_CONTRACT,
  recoverBrowserPlanCandidates,
  responsePathToControlId,
  responsePathToRepeaterContainerIds,
  schemaDefinitionToControlId,
  schemaDefinitionToResponsePath,
  summarizeReceipts,
  writeReceipt,
  type FormReceipt,
} from "tests/e2e/portable-catalog/matrix-contract";

describe("portable catalog matrix contract", () => {
  it("selects the first mechanically addressable attachment declaration", () => {
    const baseForm = {
      portableFormId: "narrative",
      previewFormId: "123e4567-e89b-12d3-a456-426614174000",
      displayName: "Narrative",
      form: { formName: "Narrative", formVersion: "1.0" },
      artifactDigests: {},
      capabilities: {
        attachment: {
          applicability: "applicable" as const,
          declarations: [
            { definition: "/properties/attachments" },
            { rulePath: "/attachments" },
          ],
          reason: null,
        },
      },
    };

    expect(firstAddressableAttachmentDefinition(baseForm)).toBe(
      "/properties/attachments",
    );
    expect(
      firstAddressableAttachmentDefinition({
        ...baseForm,
        capabilities: {
          attachment: {
            applicability: "applicable",
            declarations: [{ rulePath: "/attachments" }],
            reason: null,
          },
        },
      }),
    ).toBeUndefined();
  });

  it("maps schema definitions to stable RJSF control ids", () => {
    expect(schemaDefinitionToControlId("/properties/organization_name")).toBe(
      "organization_name",
    );
    expect(
      schemaDefinitionToControlId(
        "/properties/contact_person/properties/name/properties/first_name",
      ),
    ).toBe("contact_person--name--first_name");
    expect(
      schemaDefinitionToControlId(
        "/properties/budget_attachments/items/properties/budget_year/items/properties/start_date",
      ),
    ).toBe("budget_attachments[0]--budget_year[0]--start_date");
    expect(() => schemaDefinitionToControlId("relative/path")).toThrow(
      "absolute pointer",
    );
  });

  it("maps schema item boundaries to response wildcards", () => {
    expect(
      schemaDefinitionToResponsePath(
        "/properties/budget_attachments/items/properties/budget_year/items/properties/start_date",
      ),
    ).toBe("/budget_attachments/*/budget_year/*/start_date");
    expect(
      schemaDefinitionToResponsePath(
        "/properties/contact/properties/display~1name",
      ),
    ).toBe("/contact/display~1name");
    expect(() => schemaDefinitionToResponsePath("relative/path")).toThrow(
      "absolute pointer",
    );
  });

  it("maps response wildcards to ordered representative repeater containers", () => {
    expect(
      responsePathToRepeaterContainerIds(
        "/budget_attachments/*/budget_year/*/equipment/total",
      ),
    ).toEqual(["budget_attachments", "budget_attachments[0]--budget_year"]);
    expect(responsePathToRepeaterContainerIds("/organization/name")).toEqual(
      [],
    );
    expect(() => responsePathToRepeaterContainerIds("relative/path")).toThrow(
      "absolute pointer",
    );
    expect(() => responsePathToRepeaterContainerIds("/*/name")).toThrow(
      "wildcard has no parent",
    );
  });

  it("maps direct and nested response paths to representative FieldList controls", () => {
    expect(
      responsePathToControlId(
        "/budget_year/*/equipment/total_fund_for_attached_equipment",
      ),
    ).toBe("budget_year[0]--equipment--total_fund_for_attached_equipment");
    expect(
      responsePathToControlId(
        "/budget_attachments/*/budget_year/*/key_persons/attached_key_persons",
      ),
    ).toBe(
      "budget_attachments[0]--budget_year[0]--key_persons--attached_key_persons",
    );
    expect(() => responsePathToControlId("relative/path")).toThrow(
      "absolute pointer",
    );
    expect(() => responsePathToControlId("/*/name")).toThrow(
      "wildcard has no parent",
    );
  });

  it("classifies failures by their first failed boundary", () => {
    expect(classifyBoundary("artifact_integrity")).toBe("producer_content");
    expect(classifyBoundary("plan")).toBe("harness_inconclusive");
    expect(classifyBoundary("api_round_trip")).toBe("adapter");
    expect(classifyBoundary("apply_render")).toBe("shared_runtime");
    expect(classifyBoundary("missing_vector")).toBe("harness_inconclusive");
    expect(
      observedBoundary(new Error("ordinary failure"), "apply_render"),
    ).toBe("apply_render");
    const timeout = new Error("locator timed out");
    timeout.name = "TimeoutError";
    expect(observedBoundary(timeout, "apply_render")).toBe("timeout");
  });

  it("requires the real lower-environment preview gate", () => {
    expect(() =>
      assertPortableMatrixEnvironment({
        ENVIRONMENT: "test",
        ENABLE_PORTABLE_FORM_PREVIEW: "true",
      }),
    ).not.toThrow();
    expect(() =>
      assertPortableMatrixEnvironment({
        ENVIRONMENT: "prod",
        ENABLE_PORTABLE_FORM_PREVIEW: "true",
      }),
    ).toThrow("ENVIRONMENT=local|test|dev");
    expect(() =>
      assertPortableMatrixEnvironment({ ENVIRONMENT: "local" }),
    ).toThrow("ENABLE_PORTABLE_FORM_PREVIEW=true");
  });

  it("fails closed for missing, unsupported, empty, and duplicate plans", () => {
    expect(() => loadBrowserPlan("/path/that/does/not/exist")).toThrow(
      "does not exist",
    );
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "portable-plan-"));
    const planPath = `${directory}/plan.json`;

    fs.writeFileSync(planPath, "{not-json");
    expect(() => loadBrowserPlan(planPath)).toThrow();
    expect(recoverBrowserPlanCandidates(planPath)).toEqual([]);

    fs.writeFileSync(
      planPath,
      JSON.stringify({
        contract: "unknown",
        forms: [
          {
            portableFormId: "recoverable",
            previewFormId: "123e4567-e89b-12d3-a456-426614174000",
            artifactDigests: { "schema.json": "digest" },
          },
        ],
      }),
    );
    expect(() => loadBrowserPlan(planPath)).toThrow("unsupported");
    expect(recoverBrowserPlanCandidates(planPath)).toEqual([
      {
        portableFormId: "recoverable",
        previewFormId: "123e4567-e89b-12d3-a456-426614174000",
        artifactDigests: { "schema.json": "digest" },
      },
    ]);

    fs.writeFileSync(
      planPath,
      JSON.stringify({
        contract: PLAN_CONTRACT,
        forms: [
          {
            portableFormId: "duplicate",
            previewFormId: "123e4567-e89b-12d3-a456-426614174000",
            artifactDigests: { "schema.json": "digest-a" },
          },
          {
            portableFormId: "duplicate",
            previewFormId: "223e4567-e89b-12d3-a456-426614174000",
            artifactDigests: { "schema.json": "digest-b" },
          },
        ],
      }),
    );
    expect(() => loadBrowserPlan(planPath)).toThrow("duplicate forms");
    const recoveredDuplicates = recoverBrowserPlanCandidates(planPath);
    expect(recoveredDuplicates).toHaveLength(1);
    const recoveredReceipt: FormReceipt = {
      contract: RECEIPT_CONTRACT,
      consumerCommit: "abc",
      manifestSha256: "unavailable",
      browser: "Chrome",
      ...recoveredDuplicates[0],
      probes: [
        {
          probe: "catalog_setup",
          status: "inconclusive",
          boundary: "plan",
          ownership: "harness_inconclusive",
          durationMs: 0,
        },
      ],
    };
    completeBlockedProbes(recoveredReceipt, ["apply_render"]);
    expect(recoveredReceipt.probes).toHaveLength(2);
    expect(recoveredReceipt.probes[1]).toMatchObject({
      probe: "apply_render",
      status: "inconclusive",
      evidence: { blockedBy: "catalog_setup" },
    });

    fs.writeFileSync(
      planPath,
      JSON.stringify({ contract: PLAN_CONTRACT, forms: [] }),
    );
    expect(() => loadBrowserPlan(planPath)).toThrow("no selected forms");

    fs.writeFileSync(
      planPath,
      JSON.stringify({
        contract: PLAN_CONTRACT,
        forms: [{ portableFormId: "same" }, { portableFormId: "same" }],
      }),
    );
    expect(() => loadBrowserPlan(planPath)).toThrow("duplicate forms");
  });

  it("writes receipts and blocks release on failures or inconclusive probes", () => {
    const directory = fs.mkdtempSync(
      path.join(os.tmpdir(), "portable-receipts-"),
    );
    const receipt: FormReceipt = {
      contract: RECEIPT_CONTRACT,
      consumerCommit: "abc",
      manifestSha256: "digest",
      browser: "Chrome",
      portableFormId: "form-a",
      previewFormId: "preview-a",
      artifactDigests: {},
      probes: [
        { probe: "render", status: "passed" as const, durationMs: 1 },
        {
          probe: "vector",
          status: "inconclusive" as const,
          boundary: "missing_vector" as const,
          ownership: "harness_inconclusive" as const,
          durationMs: 0,
        },
      ],
    };

    expect(fs.existsSync(writeReceipt(directory, receipt))).toBe(true);
    completeBlockedProbes(receipt, ["render", "save", "print"]);
    expect(receipt.firstFailedBoundary).toBe("missing_vector");
    expect(receipt.firstFailureOwnership).toBe("harness_inconclusive");
    expect(receipt.probes.slice(2)).toEqual([
      {
        probe: "save",
        status: "inconclusive",
        boundary: "missing_vector",
        ownership: "harness_inconclusive",
        durationMs: 0,
        evidence: { blockedBy: "vector" },
      },
      {
        probe: "print",
        status: "inconclusive",
        boundary: "missing_vector",
        ownership: "harness_inconclusive",
        durationMs: 0,
        evidence: { blockedBy: "vector" },
      },
    ]);
    expect(summarizeReceipts([receipt])).toEqual({
      contract: "sgg-portable-browser-summary/v1",
      forms: 1,
      statuses: { failed: 0, inconclusive: 3, not_applicable: 0, passed: 1 },
      firstFailedBoundary: "missing_vector",
      firstFailureOwnership: "harness_inconclusive",
      releaseGate: false,
    });
  });

  it("summarizes an unrecoverable plan failure without form receipts", () => {
    expect(
      summarizeReceipts([], {
        probe: "catalog_setup",
        status: "inconclusive",
        boundary: "plan",
        ownership: "harness_inconclusive",
        durationMs: 0,
      }),
    ).toEqual({
      contract: "sgg-portable-browser-summary/v1",
      forms: 0,
      statuses: { failed: 0, inconclusive: 1, not_applicable: 0, passed: 0 },
      firstFailedBoundary: "plan",
      firstFailureOwnership: "harness_inconclusive",
      releaseGate: false,
    });
  });
});

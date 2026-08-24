import fs from "fs";
import os from "os";
import path from "path";
import {
  assertPortableMatrixEnvironment,
  classifyBoundary,
  completeBlockedProbes,
  loadBrowserPlan,
  observedBoundary,
  PLAN_CONTRACT,
  RECEIPT_CONTRACT,
  recoverBrowserPlanCandidates,
  summarizeReceipts,
  writeReceipt,
  type FormReceipt,
} from "tests/e2e/portable-catalog/matrix-contract";

describe("portable catalog matrix contract", () => {
  it("classifies failures by their first failed boundary", () => {
    expect(classifyBoundary("artifact_integrity")).toBe("producer_content");
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
        status: "failed",
        boundary: "plan",
        ownership: "producer_content",
        durationMs: 0,
      }),
    ).toEqual({
      contract: "sgg-portable-browser-summary/v1",
      forms: 0,
      statuses: { failed: 1, inconclusive: 0, not_applicable: 0, passed: 0 },
      firstFailedBoundary: "plan",
      firstFailureOwnership: "producer_content",
      releaseGate: false,
    });
  });
});

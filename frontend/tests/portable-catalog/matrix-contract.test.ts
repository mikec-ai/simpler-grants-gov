import fs from "fs";
import os from "os";
import path from "path";
import {
  classifyBoundary,
  loadBrowserPlan,
  PLAN_CONTRACT,
  RECEIPT_CONTRACT,
  summarizeReceipts,
  writeReceipt,
} from "tests/e2e/portable-catalog/matrix-contract";

describe("portable catalog matrix contract", () => {
  it("classifies failures by their first failed boundary", () => {
    expect(classifyBoundary("artifact_integrity")).toBe("producer_content");
    expect(classifyBoundary("api_round_trip")).toBe("adapter");
    expect(classifyBoundary("apply_render")).toBe("shared_runtime");
    expect(classifyBoundary("missing_vector")).toBe("harness_inconclusive");
  });

  it("fails closed for missing, unsupported, empty, and duplicate plans", () => {
    expect(() => loadBrowserPlan("/path/that/does/not/exist")).toThrow(
      "does not exist",
    );
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "portable-plan-"));
    const planPath = `${directory}/plan.json`;

    fs.writeFileSync(
      planPath,
      JSON.stringify({ contract: "unknown", forms: [] }),
    );
    expect(() => loadBrowserPlan(planPath)).toThrow("unsupported");

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
    const receipt = {
      contract: RECEIPT_CONTRACT,
      consumerCommit: "abc",
      manifestSha256: "digest",
      browser: "Chrome",
      portableFormId: "form-a",
      previewFormId: "preview-a",
      artifactDigests: {},
      probes: [
        { probe: "render", status: "passed" as const, durationMs: 1 },
        { probe: "vector", status: "inconclusive" as const, durationMs: 0 },
      ],
    };

    expect(fs.existsSync(writeReceipt(directory, receipt))).toBe(true);
    expect(summarizeReceipts([receipt])).toEqual({
      contract: "sgg-portable-browser-summary/v1",
      forms: 1,
      statuses: { failed: 0, inconclusive: 1, not_applicable: 0, passed: 1 },
      releaseGate: false,
    });
  });
});

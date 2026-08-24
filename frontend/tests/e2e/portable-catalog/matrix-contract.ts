import fs from "fs";
import path from "path";

export const PLAN_CONTRACT = "sgg-portable-browser-plan/v1";
export const RECEIPT_CONTRACT = "sgg-portable-browser-receipt/v1";

export type Ownership =
  "producer_content" | "adapter" | "shared_runtime" | "harness_inconclusive";

export type ProbeStatus =
  "passed" | "failed" | "not_applicable" | "inconclusive";

export type Boundary =
  | "artifact_integrity"
  | "plan"
  | "preview_registration"
  | "api_round_trip"
  | "apply_render"
  | "print_render"
  | "authentication"
  | "seed"
  | "environment"
  | "timeout"
  | "missing_vector";

export type BrowserPlanForm = {
  portableFormId: string;
  previewFormId: string;
  displayName: string;
  form: { formName: string; formVersion: string };
  artifactDigests: Record<string, string>;
  capabilities: Record<
    string,
    {
      applicability: "applicable" | "not_applicable";
      declarations: Record<string, unknown>[];
      reason: string | null;
    }
  >;
};

export type BrowserPlan = {
  contract: string;
  manifestSha256: string;
  source: { repository: string; revision: string };
  consumerSeed: { opportunityId: string };
  forms: BrowserPlanForm[];
};

export type ProbeReceipt = {
  probe: string;
  status: ProbeStatus;
  boundary?: Boundary;
  ownership?: Ownership;
  evidence?: Record<string, unknown>;
  durationMs: number;
};

export type FormReceipt = {
  contract: string;
  consumerCommit: string;
  manifestSha256: string;
  browser: string;
  portableFormId: string;
  previewFormId: string;
  artifactDigests: Record<string, string>;
  probes: ProbeReceipt[];
  firstFailedBoundary?: Boundary;
};

const ownershipByBoundary: Record<Boundary, Ownership> = {
  artifact_integrity: "producer_content",
  plan: "producer_content",
  preview_registration: "adapter",
  api_round_trip: "adapter",
  apply_render: "shared_runtime",
  print_render: "shared_runtime",
  authentication: "harness_inconclusive",
  seed: "harness_inconclusive",
  environment: "harness_inconclusive",
  timeout: "harness_inconclusive",
  missing_vector: "harness_inconclusive",
};

export function classifyBoundary(boundary: Boundary): Ownership {
  return ownershipByBoundary[boundary];
}

export function observedBoundary(error: unknown, fallback: Boundary): Boundary {
  const message = error instanceof Error ? error.message : String(error);
  return error instanceof Error &&
    (error.name === "TimeoutError" || /timeout|timed out/i.test(message))
    ? "timeout"
    : fallback;
}

export function assertPortableMatrixEnvironment(
  environment: Record<string, string | undefined> = process.env,
): void {
  const runtime = environment.ENVIRONMENT?.trim().toLowerCase();
  const enabled = ["1", "true", "yes"].includes(
    environment.ENABLE_PORTABLE_FORM_PREVIEW?.trim().toLowerCase() ?? "",
  );
  if (!runtime || !["local", "test", "dev"].includes(runtime) || !enabled) {
    throw new Error(
      "portable browser matrix requires ENVIRONMENT=local|test|dev and ENABLE_PORTABLE_FORM_PREVIEW=true",
    );
  }
}

export function loadBrowserPlan(planPath: string): BrowserPlan {
  if (!fs.existsSync(planPath)) {
    throw new Error(`portable browser plan does not exist: ${planPath}`);
  }
  const plan = JSON.parse(fs.readFileSync(planPath, "utf8")) as BrowserPlan;
  if (plan.contract !== PLAN_CONTRACT) {
    throw new Error(
      `unsupported portable browser plan contract: ${plan.contract}`,
    );
  }
  if (!Array.isArray(plan.forms) || plan.forms.length === 0) {
    throw new Error("portable browser plan has no selected forms");
  }
  const ids = plan.forms.map(({ portableFormId }) => portableFormId);
  if (new Set(ids).size !== ids.length) {
    throw new Error("portable browser plan contains duplicate forms");
  }
  return plan;
}

export function writeReceipt(directory: string, receipt: FormReceipt): string {
  fs.mkdirSync(directory, { recursive: true });
  const receiptPath = path.join(
    directory,
    `${receipt.portableFormId}-${receipt.browser}.json`,
  );
  fs.writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
  return receiptPath;
}

export function completeBlockedProbes(
  receipt: FormReceipt,
  plannedProbes: readonly string[],
): void {
  const firstFailure = receipt.probes.find(
    ({ status }) => status === "failed" || status === "inconclusive",
  );
  if (!firstFailure) return;
  receipt.firstFailedBoundary = firstFailure.boundary;
  for (const probeName of plannedProbes) {
    if (receipt.probes.some(({ probe }) => probe === probeName)) continue;
    receipt.probes.push({
      probe: probeName,
      status: "inconclusive",
      boundary: firstFailure.boundary,
      ownership: firstFailure.ownership,
      durationMs: 0,
      evidence: { blockedBy: firstFailure.probe },
    });
  }
}

export function summarizeReceipts(receipts: FormReceipt[]) {
  const statuses: Record<ProbeStatus, number> = {
    passed: 0,
    failed: 0,
    not_applicable: 0,
    inconclusive: 0,
  };
  for (const receipt of receipts) {
    for (const probe of receipt.probes) {
      statuses[probe.status] += 1;
    }
  }
  const firstFailedBoundary = receipts
    .flatMap(({ probes }) => probes)
    .find(
      ({ status }) => status === "failed" || status === "inconclusive",
    )?.boundary;
  return {
    contract: "sgg-portable-browser-summary/v1",
    forms: receipts.length,
    statuses,
    firstFailedBoundary: firstFailedBoundary ?? null,
    releaseGate: statuses.failed === 0 && statuses.inconclusive === 0,
  };
}

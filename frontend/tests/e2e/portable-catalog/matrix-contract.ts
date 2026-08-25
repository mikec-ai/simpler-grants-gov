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

export type SchemaImplicationField = {
  schemaPath: string;
  responsePath: string;
  title: string | null;
  constraint: Record<string, unknown> | null;
};

export type SchemaImplicationDeclaration = {
  objectSchemaPath: string;
  objectResponsePath: string;
  trigger: SchemaImplicationField;
  consequence: SchemaImplicationField & { required: true };
};

export type BrowserPlan = {
  contract: string;
  manifestSha256: string;
  source: { repository: string; revision: string };
  consumerSeed: { opportunityId: string; competitionId: string };
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
  firstFailureOwnership?: Ownership;
};

export type RecoveredPlanCandidate = Pick<
  BrowserPlanForm,
  "portableFormId" | "previewFormId" | "artifactDigests"
>;

export function firstAddressableAttachmentDefinition(
  form: BrowserPlanForm,
): string | undefined {
  const capability = form.capabilities.attachment;
  if (capability?.applicability !== "applicable") return undefined;
  return capability.declarations.find(
    ({ definition }) => typeof definition === "string",
  )?.definition as string | undefined;
}

export function schemaDefinitionToControlId(definition: string): string {
  if (!definition.startsWith("/")) {
    throw new Error(
      `schema definition is not an absolute pointer: ${definition}`,
    );
  }
  const parts: string[] = [];
  for (const encoded of definition.slice(1).split("/")) {
    const segment = encoded.replaceAll("~1", "/").replaceAll("~0", "~");
    if (segment === "properties" || !segment) continue;
    if (segment === "items") {
      if (!parts.length) {
        throw new Error(`schema items segment has no parent: ${definition}`);
      }
      parts[parts.length - 1] = `${parts.at(-1)}[0]`;
    } else {
      parts.push(segment);
    }
  }
  if (!parts.length) {
    throw new Error(
      `schema definition does not identify a control: ${definition}`,
    );
  }
  return parts.join("--");
}

export function schemaDefinitionToResponsePath(definition: string): string {
  if (!definition.startsWith("/")) {
    throw new Error(
      `schema definition is not an absolute pointer: ${definition}`,
    );
  }
  const parts: string[] = [];
  for (const encoded of definition.slice(1).split("/")) {
    const segment = encoded.replaceAll("~1", "/").replaceAll("~0", "~");
    if (segment === "properties" || !segment) continue;
    parts.push(segment === "items" ? "*" : segment);
  }
  if (!parts.length) {
    throw new Error(
      `schema definition does not identify a response path: ${definition}`,
    );
  }
  return `/${parts
    .map((segment) => segment.replaceAll("~", "~0").replaceAll("/", "~1"))
    .join("/")}`;
}

export function responsePathToControlId(responsePath: string): string {
  if (!responsePath.startsWith("/")) {
    throw new Error(
      `response path is not an absolute pointer: ${responsePath}`,
    );
  }
  const parts: string[] = [];
  for (const encoded of responsePath.slice(1).split("/")) {
    const segment = encoded.replaceAll("~1", "/").replaceAll("~0", "~");
    if (segment === "*") {
      if (!parts.length) {
        throw new Error(`response wildcard has no parent: ${responsePath}`);
      }
      parts[parts.length - 1] = `${parts.at(-1)}[0]`;
    } else if (segment) {
      parts.push(segment);
    }
  }
  if (!parts.length) {
    throw new Error(
      `response path does not identify a control: ${responsePath}`,
    );
  }
  return parts.join("--");
}

export function responsePathToRepeaterContainerIds(
  responsePath: string,
): string[] {
  if (!responsePath.startsWith("/")) {
    throw new Error(
      `response path is not an absolute pointer: ${responsePath}`,
    );
  }
  const parts: string[] = [];
  const containerIds: string[] = [];
  for (const encoded of responsePath.slice(1).split("/")) {
    const segment = encoded.replaceAll("~1", "/").replaceAll("~0", "~");
    if (segment === "*") {
      if (!parts.length) {
        throw new Error(`response wildcard has no parent: ${responsePath}`);
      }
      containerIds.push(parts.join("--"));
      parts[parts.length - 1] = `${parts.at(-1)}[0]`;
    } else if (segment) {
      parts.push(segment);
    }
  }
  return containerIds;
}

const ownershipByBoundary: Record<Boundary, Ownership> = {
  artifact_integrity: "producer_content",
  plan: "harness_inconclusive",
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

export function boundaryError(boundary: Boundary, message: string): Error {
  return Object.assign(new Error(message), { boundary });
}

export function observedBoundary(error: unknown, fallback: Boundary): Boundary {
  const declaredBoundary = (error as { boundary?: unknown } | null)?.boundary;
  if (
    typeof declaredBoundary === "string" &&
    Object.hasOwn(ownershipByBoundary, declaredBoundary)
  ) {
    return declaredBoundary as Boundary;
  }
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

export function recoverBrowserPlanCandidates(
  planPath: string,
): RecoveredPlanCandidate[] {
  if (!fs.existsSync(planPath)) return [];
  let document: unknown;
  try {
    document = JSON.parse(fs.readFileSync(planPath, "utf8"));
  } catch {
    return [];
  }
  if (!document || typeof document !== "object") return [];
  const forms = (document as { forms?: unknown }).forms;
  if (!Array.isArray(forms)) return [];
  const candidates = forms.filter((form): form is RecoveredPlanCandidate => {
    if (!form || typeof form !== "object") return false;
    const candidate = form as RecoveredPlanCandidate;
    return (
      /^[a-z0-9][a-z0-9-]*$/.test(candidate.portableFormId) &&
      /^[a-f0-9-]{36}$/.test(candidate.previewFormId) &&
      !!candidate.artifactDigests &&
      typeof candidate.artifactDigests === "object" &&
      !Array.isArray(candidate.artifactDigests) &&
      Object.values(candidate.artifactDigests).every(
        (digest) => typeof digest === "string",
      )
    );
  });
  return candidates.filter(
    (candidate, index) =>
      candidates.findIndex(
        ({ portableFormId }) => portableFormId === candidate.portableFormId,
      ) === index,
  );
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
  receipt.firstFailureOwnership = firstFailure.ownership;
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

export function summarizeReceipts(
  receipts: FormReceipt[],
  catalogFailure?: ProbeReceipt,
) {
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
  if (catalogFailure && receipts.length === 0) {
    statuses[catalogFailure.status] += 1;
  }
  const firstFailure =
    receipts
      .flatMap(({ probes }) => probes)
      .find(({ status }) => status === "failed" || status === "inconclusive") ??
    catalogFailure;
  return {
    contract: "sgg-portable-browser-summary/v1",
    forms: receipts.length,
    statuses,
    firstFailedBoundary: firstFailure?.boundary ?? null,
    firstFailureOwnership: firstFailure?.ownership ?? null,
    releaseGate: statuses.failed === 0 && statuses.inconclusive === 0,
  };
}

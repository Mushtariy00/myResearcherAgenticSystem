/**
 * Test-only: the Studio run page against a fake API (the generated client's requests go to a
 * fetch mock, live events to a FakeEventSource), with runs built from the demo fixtures. Test
 * files still declare their own `vi.mock` calls (next/navigation, sonner, canvas-confetti, the
 * PDF viewer and ECharts), since mocks are hoisted per file.
 */
import { waitFor } from "@testing-library/react";
import type {
  ApprovalOut,
  ArtifactList,
  ArtifactOut,
  OutputVersionOut,
  ProjectOut,
  RunDetail,
  StageDetail,
  StageInfo,
  StageOutputOut,
} from "@/client";
import { installEventSource, json, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import {
  attemptOut,
  DEMO_OUTPUTS,
  runDetailOut,
  stageDetailOut,
  stageOutputOut,
  stageRunOut,
  versionOut,
} from "@/lib/stage-output.fixtures";
import { STAGE_ORDER } from "@/lib/timeline";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { StudioRunPage } from "./studio-run-page";

export const RUN_ID = runDetailOut().id;
export const PROJECT_ID = runDetailOut().project_id;

export const PROJECT: ProjectOut = {
  id: PROJECT_ID,
  name: "Depth lab",
  description: "",
  privacy: "standard",
  allow_free_models: true,
  created_by: "owner",
  created_at: "2026-10-01T00:00:00Z",
  my_role: "owner",
};

const STAGES: StageInfo[] = STAGE_ORDER.map((id, position) => ({
  id,
  position,
  auto_approvable: id !== "coding",
}));

export type FakeRunApi = {
  run: RunDetail;
  stages: Record<string, StageDetail>;
  artifacts: ArtifactList;
  /** Answers POST /approvals with the request's JSON body. */
  decide: (body: Record<string, unknown>) => Response | Promise<Response>;
  /** Answers POST /retry?stage=. */
  retry: (stage: string | null) => Response | Promise<Response>;
};

export const accepted = () => json(202, { status: "accepted" });

/** The fake API of one test; tests change its fields to change what the API answers. */
export const api: FakeRunApi = {
  run: runDetailOut(),
  stages: {},
  artifacts: { run_id: RUN_ID, items: [], demo: false },
  decide: accepted,
  retry: accepted,
};

let fetchMock: ReturnType<typeof mockApi> | undefined;

/** Call in beforeEach: browser fakes, the event stream and the fake API, all reset. */
export function setUpRunPage(): void {
  installDomFakes();
  installEventSource();
  api.run = runDetailOut();
  api.stages = {};
  api.artifacts = { run_id: RUN_ID, items: [], demo: false };
  api.decide = accepted;
  api.retry = accepted;
  fetchMock = mockApi(async (request, path) => {
    if (request.method === "POST") {
      if (path === `/api/v1/runs/${RUN_ID}/approvals`) {
        return api.decide((await request.clone().json()) as Record<string, unknown>);
      }
      if (path === `/api/v1/runs/${RUN_ID}/retry`) {
        return api.retry(new URL(request.url).searchParams.get("stage"));
      }
      if (path === `/api/v1/runs/${RUN_ID}/cancel`) {
        return accepted();
      }
    }
    if (path === `/api/v1/runs/${RUN_ID}`) {
      // A run with another id stands for one the visitor cannot open.
      return api.run.id === RUN_ID ? json(200, api.run) : json(404, { detail: "run.not_found" });
    }
    if (path === "/api/v1/stages") {
      return json(200, STAGES);
    }
    if (path === "/api/v1/projects") {
      return json(200, [PROJECT]);
    }
    if (path === `/api/v1/runs/${RUN_ID}/artifacts`) {
      return json(200, api.artifacts);
    }
    const stage = path.match(/^\/api\/v1\/runs\/[^/]+\/stages\/([a-z_]+)$/)?.[1];
    if (stage) {
      return json(200, api.stages[stage] ?? stageDetailOut(RUN_ID, stage, []));
    }
    if (path.startsWith("/api/v1/papers/")) {
      return json(404, { detail: "paper.not_found" });
    }
    return json(404, { detail: "run.not_found" });
  });
}

/** Requests sent so far, as "METHOD /path?query". */
export function sentRequests(): string[] {
  return fetchMock ? requestsOf(fetchMock) : [];
}

/** JSON bodies of the decisions sent so far. */
export async function sentDecisions(): Promise<unknown[]> {
  const calls = fetchMock?.mock.calls ?? [];
  const bodies: unknown[] = [];
  for (const [input] of calls) {
    const request = input as Request;
    if (request.method === "POST" && new URL(request.url).pathname.endsWith("/approvals")) {
      bodies.push(await request.clone().json());
    }
  }
  return bodies;
}

export function renderRunPage(locale: "en" | "ko" = "en") {
  return renderStudio(<StudioRunPage runId={RUN_ID} />, {
    user: TEST_USER,
    queryClient: makeQueryClient(),
    locale,
  });
}

/** Waits until the page shows the run (its title). */
export async function waitForRun(topic = api.run.topic): Promise<void> {
  await waitFor(() => {
    const title = document.getElementById("run-title");
    if (title?.textContent !== topic) {
      throw new Error("The run is not on screen yet");
    }
  });
}

export function approvedBy(name: string): ApprovalOut {
  return {
    decision: "approve",
    comment: "",
    actor_id: name.toLowerCase(),
    actor_name: name,
    at: "2026-10-30T02:00:00Z",
  };
}

/** A run detail output and its stage detail version with the same id and hash. */
export function outputPair(
  data: Record<string, unknown>,
  overrides: Partial<OutputVersionOut> = {},
): { version: OutputVersionOut; output: StageOutputOut } {
  const version = versionOut(data, overrides);
  const output = stageOutputOut(data, {
    id: version.id,
    sha256: version.sha256,
    version: version.version,
    degraded: version.degraded,
    degraded_reason: version.degraded_reason,
  });
  return { version, output };
}

/** A completed run: every stage approved once, with the demo outputs. */
export function seedCompletedRun(): void {
  const outputs = STAGE_ORDER.map((stage) => ({
    stage,
    ...outputPair(DEMO_OUTPUTS[stage], { approval: approvedBy("Alice") }),
  }));
  api.run = runDetailOut({
    status: "completed",
    stages: outputs.map(({ stage, output }) =>
      stageRunOut(stage, "approved", { outputs: [output], finished_at: "2026-10-30T03:00:00Z" }),
    ),
  });
  api.stages = Object.fromEntries(
    outputs.map(({ stage, version }) => [
      stage,
      stageDetailOut(RUN_ID, stage, [attemptOut(1, [version], { status: "approved" })]),
    ]),
  );
}

export function artifact(
  stage: string,
  kind: ArtifactOut["kind"],
  filename: string,
  stageOutputId: string,
): ArtifactOut {
  return {
    id: `${stageOutputId}.${kind}.${filename}`,
    stage,
    kind,
    filename,
    path: null,
    media_type: "text/plain",
    size_bytes: 2048,
    sha256: "c".repeat(64),
    stage_output_id: stageOutputId,
    version: 1,
    created_at: "2026-10-30T03:00:00Z",
    demo: true,
  };
}

// @vitest-environment jsdom
import { cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ArtifactList, ArtifactOut } from "@/client";
import { client } from "@/client/client.gen";
import { BASE_URL, json, mockApi, renderWithQuery, requestsOf } from "./run-hooks.fixtures";
import { artifactUrl, useRunArtifacts } from "./use-run-artifacts";

const RUN_ID = "22222222-2222-4222-8222-222222222222";
const CODING_OUTPUT = "44444444-4444-4444-8444-444444444444";
const WRITING_OUTPUT = "55555555-5555-4555-8555-555555555555";

function artifact(
  id: string,
  stage: string,
  kind: ArtifactOut["kind"],
  filename: string,
  extra: Partial<ArtifactOut> = {},
): ArtifactOut {
  return {
    id,
    stage,
    kind,
    filename,
    path: null,
    media_type: "text/plain",
    size_bytes: 1024,
    sha256: "c".repeat(64),
    stage_output_id: stage === "writing" ? WRITING_OUTPUT : CODING_OUTPUT,
    version: 1,
    created_at: "2026-10-30T01:00:00Z",
    demo: true,
    ...extra,
  };
}

const list: ArtifactList = {
  run_id: RUN_ID,
  items: [
    artifact(`${CODING_OUTPUT}.archive`, "coding", "code_archive", "depthnet-code.zip", {
      media_type: "application/zip",
    }),
    artifact(`${CODING_OUTPUT}.file-0`, "coding", "code_file", "model.py", { path: "model.py" }),
    artifact(`${WRITING_OUTPUT}.draft`, "writing", "draft", "draft.md", {
      media_type: "text/markdown",
    }),
  ],
  demo: true,
};

let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  fetchMock = mockApi((_request, path) =>
    path === `/api/v1/runs/${RUN_ID}/artifacts`
      ? json(200, list)
      : json(404, { detail: "run.not_found" }),
  );
});

afterEach(cleanup);

describe("useRunArtifacts", () => {
  it("lists the run's files by stage, with the code archive and the demo flag", async () => {
    const { result } = renderWithQuery(() => useRunArtifacts(RUN_ID));
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    expect(requestsOf(fetchMock)).toEqual([`GET /api/v1/runs/${RUN_ID}/artifacts`]);
    expect(result.current.artifacts).toEqual(list.items);
    expect(Object.keys(result.current.byStage)).toEqual(["coding", "writing"]);
    expect(result.current.byStage.coding?.map((item) => item.filename)).toEqual([
      "depthnet-code.zip",
      "model.py",
    ]);
    expect(result.current.codeArchive?.filename).toBe("depthnet-code.zip");
    expect(result.current.demo).toBe(true);
  });

  it("is empty while loading, and can wait to be enabled", () => {
    const { result } = renderWithQuery(() => useRunArtifacts(RUN_ID, { enabled: false }));
    expect(result.current).toMatchObject({
      artifacts: [],
      byStage: {},
      codeArchive: undefined,
      demo: false,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("artifactUrl", () => {
  it("is the download path, with the id escaped", () => {
    expect(artifactUrl(`${CODING_OUTPUT}.archive`)).toBe(
      `${BASE_URL}/api/v1/artifacts/${CODING_OUTPUT}.archive`,
    );
    expect(artifactUrl("a/b?c")).toBe(`${BASE_URL}/api/v1/artifacts/a%2Fb%3Fc`);
  });

  it("stays same-origin when the client has no base URL (the browser)", () => {
    client.setConfig({ baseUrl: undefined });
    expect(artifactUrl("x.draft")).toBe("/api/v1/artifacts/x.draft");
  });
});

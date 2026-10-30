// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectSettings } from "@/client";
import { getProjectQueryKey } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { projectSettingsFieldError, useProjectSettings } from "./use-project-settings";

const PROJECT = "33333333-3333-4333-8333-333333333333";
const PATH = `/api/v1/projects/${PROJECT}/settings`;

const SAVED: ProjectSettings = {
  privacy: "standard",
  allow_free_models: true,
  auto_approve: false,
  approval_expiry_days: 7,
};

const fetchMock = vi.fn<typeof fetch>();
let stored: ProjectSettings = SAVED;
let puts: ProjectSettings[] = [];
let putResponse: (body: ProjectSettings) => Promise<Response>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  stored = SAVED;
  puts = [];
  putResponse = async (body) => {
    stored = body;
    return json(200, body);
  };
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    if (path === PATH && request.method === "PUT") {
      const body = (await request.json()) as ProjectSettings;
      puts.push(body);
      return putResponse(body);
    }
    if (path === PATH) {
      return json(200, stored);
    }
    return json(200, {});
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { ...renderHook(() => useProjectSettings(PROJECT), { wrapper }), queryClient };
}

describe("useProjectSettings", () => {
  it("loads the settings into the form", async () => {
    stored = { ...SAVED, privacy: "confidential", approval_expiry_days: 3 };
    const { result } = setup();
    await waitFor(() => expect(result.current.settings).toEqual(stored));
    await waitFor(() => expect(result.current.form.getValues()).toEqual(stored));
    expect(result.current.isDirty).toBe(false);
  });

  it("keeps a field the user is editing when the saved settings change", async () => {
    const { result, queryClient } = setup();
    await waitFor(() => expect(result.current.form.getValues()).toEqual(SAVED));
    act(() => result.current.form.setValue("approval_expiry_days", 12, { shouldDirty: true }));
    await waitFor(() => expect(result.current.isDirty).toBe(true));

    // Someone else switched free models off; the reload must not undo the edit.
    stored = { ...SAVED, allow_free_models: false };
    await act(async () => {
      await queryClient.refetchQueries();
    });
    await waitFor(() => expect(result.current.form.getValues("allow_free_models")).toBe(false));
    expect(result.current.form.getValues("approval_expiry_days")).toBe(12);
  });

  it("applies a switch at once and saves it on top of the latest settings", async () => {
    let release: (response: Response) => void = () => {};
    putResponse = (body) =>
      new Promise<Response>((resolve) => {
        release = (response) => {
          stored = body;
          resolve(response);
        };
      });
    const { result, queryClient } = setup();
    const projectKey = getProjectQueryKey({ path: { project_id: PROJECT } });
    queryClient.setQueryData(projectKey, {} as never);
    await waitFor(() => expect(result.current.settings).toEqual(SAVED));

    let saving: Promise<unknown> = Promise.resolve();
    act(() => {
      saving = result.current.update({ auto_approve: true });
    });
    await waitFor(() => expect(result.current.settings?.auto_approve).toBe(true));
    expect(result.current.isSaving).toBe(true);
    await waitFor(() => expect(puts).toEqual([{ ...SAVED, auto_approve: true }]));

    let outcome: unknown;
    await act(async () => {
      release(json(200, { ...SAVED, auto_approve: true }));
      outcome = await saving;
    });
    expect(outcome).toEqual({ ok: true, data: { ...SAVED, auto_approve: true } });
    expect(result.current.saveError).toBeNull();
    await waitFor(() => expect(result.current.form.getValues("auto_approve")).toBe(true));
    expect(result.current.isDirty).toBe(false);
    // Privacy and free models also live on the project.
    expect(queryClient.getQueryState(projectKey)?.isInvalidated).toBe(true);
  });

  it("puts a refused change back and says why", async () => {
    putResponse = async () => json(403, { detail: "permission.denied" });
    const { result } = setup();
    await waitFor(() => expect(result.current.settings).toEqual(SAVED));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.update({ privacy: "confidential" });
    });
    expect(outcome).toMatchObject({ ok: false, error: { code: "permission.denied" } });
    expect(result.current.saveError?.code).toBe("permission.denied");
    expect(result.current.settings).toEqual(SAVED);

    act(() => result.current.clearSaveError());
    expect(result.current.saveError).toBeNull();
  });

  it("saves changes one after another, so the last one wins", async () => {
    const releases: Array<() => void> = [];
    putResponse = (body) =>
      new Promise<Response>((resolve) => {
        releases.push(() => {
          stored = body;
          resolve(json(200, body));
        });
      });
    const { result } = setup();
    await waitFor(() => expect(result.current.settings).toEqual(SAVED));

    let first: Promise<unknown> = Promise.resolve();
    let second: Promise<unknown> = Promise.resolve();
    act(() => {
      first = result.current.update({ auto_approve: true });
    });
    await waitFor(() => expect(puts).toHaveLength(1));
    act(() => {
      second = result.current.update({ allow_free_models: false });
    });
    await waitFor(() => expect(result.current.settings?.allow_free_models).toBe(false));
    // The second save waits for the first one.
    expect(puts).toHaveLength(1);

    await act(async () => {
      releases[0]?.();
      await first;
    });
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1]).toEqual({ ...SAVED, auto_approve: true, allow_free_models: false });
    await act(async () => {
      releases[1]?.();
      await second;
    });
    expect(result.current.settings).toEqual({
      ...SAVED,
      auto_approve: true,
      allow_free_models: false,
    });
  });

  it("validates and saves the whole form", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.form.getValues()).toEqual(SAVED));

    act(() => result.current.form.setValue("approval_expiry_days", 0, { shouldDirty: true }));
    await waitFor(() => expect(result.current.isDirty).toBe(true));
    await act(async () => {
      await result.current.submit();
    });
    expect(puts).toEqual([]);
    const { error } = result.current.form.getFieldState("approval_expiry_days");
    expect(projectSettingsFieldError(error)).toEqual({
      code: "approvalExpiryDays.outOfRange",
      key: "project.settings.errors.approvalExpiryDays.outOfRange",
      values: { min: 1, max: 30 },
    });

    // Typed into a text input: saved as a number, and shown as the saved value afterwards.
    act(() => result.current.form.setValue("approval_expiry_days", "14", { shouldDirty: true }));
    await act(async () => {
      await result.current.submit();
    });
    expect(puts).toEqual([{ ...SAVED, approval_expiry_days: 14 }]);
    await waitFor(() => expect(result.current.isDirty).toBe(false));
    await waitFor(() => expect(result.current.settings?.approval_expiry_days).toBe(14));
    expect(result.current.form.getValues("approval_expiry_days")).toBe(14);
  });
});

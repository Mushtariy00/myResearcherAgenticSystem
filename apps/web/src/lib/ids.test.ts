import { describe, expect, it, vi } from "vitest";
import { isUuid } from "./ids";

vi.mock("next-intl/server", () => ({ getTranslations: vi.fn(async () => (key: string) => key) }));
vi.mock("next/navigation", () => ({
  notFound: vi.fn((): never => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
// The pages only choose between not found and their view; the views have their own tests.
vi.mock("@/components/projects/project-view", () => ({ ProjectView: () => null }));
vi.mock("@/components/projects/new-run/new-run-view", () => ({ NewRunView: () => null }));
vi.mock("@/components/runs/run-view", () => ({ RunView: () => null }));
vi.mock("@/studio/components/runs/studio-run-page", () => ({ StudioRunPage: () => null }));
vi.mock("@/studio/components/projects/studio-project-view", () => ({
  StudioProjectView: () => null,
}));

const ID = "33333333-3333-4333-8333-333333333333";

describe("isUuid", () => {
  it("accepts the ids the API hands out, as FastAPI reads them", () => {
    expect(isUuid(ID)).toBe(true);
    expect(isUuid(ID.toUpperCase())).toBe(true);
    expect(isUuid(ID.replaceAll("-", ""))).toBe(true);
  });

  it("refuses truncated or mistyped ids", () => {
    for (const value of ["abc", ID.slice(0, -1), `${ID}x`, `${ID}/runs`, "", "../admin"]) {
      expect(isUuid(value), value).toBe(false);
    }
  });
});

const params = (id: string) => ({ params: Promise.resolve({ id }) });

describe("pages with an id in the URL", () => {
  it("are not found for a malformed id, in both interfaces", async () => {
    const pages = await Promise.all([
      import("@/app/(app)/projects/[id]/page"),
      import("@/app/(app)/projects/[id]/runs/new/page"),
      import("@/app/(app)/runs/[id]/page"),
      import("@/app/studio/(app)/runs/[id]/page"),
    ]);
    for (const page of pages) {
      await expect(page.default(params("abc"))).rejects.toThrow("NEXT_NOT_FOUND");
      await expect(page.default(params(ID))).resolves.toBeTruthy();
    }
    const studioProject = await import("@/app/studio/(app)/projects/[id]/page");
    const query = { searchParams: Promise.resolve({}) };
    await expect(studioProject.default({ ...params("abc"), ...query })).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
    await expect(studioProject.default({ ...params(ID), ...query })).resolves.toBeTruthy();
  });
});

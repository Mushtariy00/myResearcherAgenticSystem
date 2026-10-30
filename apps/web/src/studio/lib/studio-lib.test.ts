import { describe, expect, it } from "vitest";
import { studioLoginHref } from "./login-redirect";
import { riseDelay, staggerDelay } from "./motion";
import { activeNavId, studioBreadcrumbs, visibleNav } from "./nav";
import { beamState } from "./stages";

describe("studioLoginHref", () => {
  it("brings the visitor back to the page and its query", () => {
    expect(studioLoginHref("/studio/runs/r1", "?tab=log")).toBe(
      "/studio/login?next=%2Fstudio%2Fruns%2Fr1%3Ftab%3Dlog",
    );
    expect(studioLoginHref("/studio/papers", "q=x")).toBe(
      "/studio/login?next=%2Fstudio%2Fpapers%3Fq%3Dx",
    );
  });

  it("needs no next for the dashboard or the landing page", () => {
    expect(studioLoginHref("/studio/dashboard")).toBe("/studio/login");
    expect(studioLoginHref("/studio")).toBe("/studio/login");
  });
});

describe("Studio navigation", () => {
  it("shows Admin to lab admins only", () => {
    expect(visibleNav("user").map((item) => item.id)).toEqual([
      "dashboard",
      "projects",
      "papers",
      "notifications",
    ]);
    expect(visibleNav("admin").map((item) => item.id)).toContain("admin");
  });

  it("highlights the section a page belongs to", () => {
    expect(activeNavId("/studio/dashboard")).toBe("dashboard");
    expect(activeNavId("/studio/projects/p1")).toBe("projects");
    expect(activeNavId("/studio/runs/r1")).toBe("projects");
    expect(activeNavId("/studio/papers/42")).toBe("papers");
    expect(activeNavId("/studio/adminx")).toBeNull();
  });

  it("builds breadcrumbs with links for every crumb but the current page", () => {
    expect(studioBreadcrumbs("/studio/projects/p1")).toEqual([
      { key: "dashboard", label: { kind: "nav", id: "dashboard" }, href: "/studio/dashboard" },
      {
        key: "projects",
        label: { kind: "nav", id: "projects" },
        href: "/studio/dashboard#projects",
      },
      { key: "project:p1", label: { kind: "project", id: "p1" } },
    ]);
    expect(studioBreadcrumbs("/studio/dashboard")).toEqual([
      { key: "dashboard", label: { kind: "nav", id: "dashboard" } },
    ]);
    expect(studioBreadcrumbs("/studio/some%20page")).toEqual([
      { key: "some%20page", label: { kind: "text", text: "some page" } },
    ]);
  });
});

describe("pipeline beams", () => {
  it("flow only from an approved stage into a running one", () => {
    expect(beamState("approved", "running")).toBe("flowing");
    expect(beamState("approved", "output_ready")).toBe("complete");
    expect(beamState("approved", "approved")).toBe("complete");
    expect(beamState("approved", "pending")).toBe("idle");
    expect(beamState("running", "pending")).toBe("idle");
    expect(beamState("failed", "running")).toBe("idle");
  });
});

describe("staggered reveals", () => {
  it("space items 40 ms apart and cap the delay at the twelfth item", () => {
    expect(staggerDelay(0)).toBe(0);
    expect(staggerDelay(1)).toBeCloseTo(0.04);
    expect(staggerDelay(50)).toBeCloseTo(0.44);
    expect(riseDelay(2, 100)).toBe("180ms");
  });
});

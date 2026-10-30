// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { CompassIcon } from "lucide-react";
import { afterEach, describe, expect, it } from "vitest";
import { renderStudio } from "@/studio/test/render";
import { StudioStatePanel } from "./studio-state-panel";

afterEach(() => {
  cleanup();
});

describe("StudioStatePanel", () => {
  it("is the page by default: its title is the page's h1, centred in the content area", () => {
    const { container } = renderStudio(
      <StudioStatePanel
        icon={<CompassIcon aria-hidden />}
        code="404"
        title="Not in Studio yet"
        description="This page does not exist."
        action={{ href: "/studio/dashboard", label: "Go to the dashboard" }}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Not in Studio yet" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to the dashboard" }).getAttribute("href")).toBe(
      "/studio/dashboard",
    );
    expect(container.firstElementChild?.className).toMatch(/min-h-\[60vh\]/);
  });

  it("fits into a page section with the heading level it is given and no page height", () => {
    const { container } = renderStudio(
      <section aria-labelledby="projects">
        <h2 id="projects">Projects</h2>
        <StudioStatePanel
          variant="section"
          headingLevel={3}
          icon={<CompassIcon aria-hidden />}
          title="No projects yet"
          description="Create a project."
        />
      </section>,
    );
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByRole("heading", { level: 3, name: "No projects yet" })).toBeTruthy();
    expect(container.innerHTML).not.toMatch(/min-h-\[60vh\]/);
  });
});

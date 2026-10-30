// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import type { MeOut, ProjectOut } from "@/client";
import { getMeQueryKey, listProjectsQueryKey } from "@/client/@tanstack/react-query.gen";
import { unreadNotificationsQueryKey } from "@/studio/hooks/use-unread-notifications";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { StudioDashboard } from "./studio-dashboard";

const ME: MeOut = {
  id: TEST_USER.id,
  email: TEST_USER.email,
  name: TEST_USER.name,
  role: TEST_USER.role,
  budget_usd: "50.00",
  spent_usd: "12.50",
};

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
});

function renderDashboard(projects: ProjectOut[], locale: "en" | "ko" = "en") {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(getMeQueryKey(), ME);
  queryClient.setQueryData(listProjectsQueryKey(), projects);
  queryClient.setQueryData(unreadNotificationsQueryKey, 0);
  return renderStudio(<StudioDashboard />, { user: TEST_USER, queryClient, locale });
}

describe("StudioDashboard without projects", () => {
  it("keeps the greeting as the only h1 and shows the empty list inside the Projects section", () => {
    const { container } = renderDashboard([]);
    const [title, ...others] = screen.getAllByRole("heading", { level: 1 });
    expect(others).toHaveLength(0);
    expect(title?.textContent).toMatch(/Ada Lovelace/);

    const projects = screen.getByRole("region", { name: "Projects" });
    expect(
      within(projects).getByRole("heading", { level: 3, name: "No projects yet" }),
    ).toBeTruthy();
    // A compact panel, not one sized for a whole page.
    expect(container.innerHTML).not.toMatch(/min-h-\[60vh\]/);
  });

  it("says the same in Korean", () => {
    renderDashboard([], "ko");
    const projects = screen.getByRole("region", { name: "프로젝트" });
    expect(within(projects).getByRole("heading", { level: 3 })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

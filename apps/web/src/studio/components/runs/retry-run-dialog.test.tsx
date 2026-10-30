// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { json } from "@/hooks/run-hooks.fixtures";
import {
  DEMO_LITERATURE,
  runDetailOut,
  stageOutputOut,
  stageRunOut,
} from "@/lib/stage-output.fixtures";
import {
  api,
  RUN_ID,
  renderRunPage,
  sentRequests,
  setUpRunPage,
  waitForRun,
} from "./run-page.fixtures";

const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.search),
  usePathname: () => "/studio/runs/22222222-2222-4222-8222-222222222222",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast }));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));
vi.mock("@/components/shared/pdf-viewer", () => ({ PdfViewer: () => null }));

/** The method stage failed after the literature output was approved. */
function seedFailedRun() {
  api.run = runDetailOut({
    status: "failed",
    error: "stage.error",
    stages: [
      stageRunOut("literature", "approved", { outputs: [stageOutputOut(DEMO_LITERATURE)] }),
      stageRunOut("method", "failed", { error: "stage.error" }),
    ],
  });
}

beforeEach(() => {
  navigation.search = "";
  setUpRunPage();
  seedFailedRun();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function openRetry() {
  renderRunPage();
  await waitForRun();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  return screen.findByRole("dialog", { name: "Run again from a stage" });
}

describe("RetryRunDialog", () => {
  it("retries from a chosen stage and says which outputs become outdated", async () => {
    const dialog = await openRetry();
    const literature = within(dialog).getByRole("radio", {
      name: /Literature/,
    }) as HTMLInputElement;
    const method = within(dialog).getByRole("radio", { name: /Method/ }) as HTMLInputElement;
    // The stage where the run stopped comes first to mind.
    expect(method.checked).toBe(true);
    expect(within(dialog).getByText("Approved outputs before Method are kept.")).toBeTruthy();
    expect(
      within(dialog).getByText(/^Method runs again: its current output becomes outdated/),
    ).toBeTruthy();

    fireEvent.click(literature);
    expect(literature.checked).toBe(true);
    expect(within(dialog).getByText("Nothing is kept: the whole run starts over.")).toBeTruthy();
    expect(
      within(dialog).getByText(
        /^Literature and Method run again: their current outputs become outdated/,
      ),
    ).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Retry from Literature" }));
    await waitFor(() =>
      expect(sentRequests()).toContain(`POST /api/v1/runs/${RUN_ID}/retry?stage=literature`),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("The run starts again from Literature."),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows why the API refused the retry", async () => {
    api.retry = () => json(409, { detail: "run.not_retryable" });
    const dialog = await openRetry();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry from Method" }));
    const alert = await within(dialog).findByRole("alert");
    expect(alert.textContent).toContain("The retry did not start");
    expect(alert.textContent).toContain(
      "This run is still in progress, so it can't be retried yet.",
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("opens with the failed stage chosen from its panel", async () => {
    navigation.search = "stage=method";
    renderRunPage();
    await waitForRun();
    expect(await screen.findByRole("heading", { level: 4, name: "Method failed" })).toBeTruthy();
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText("A stage failed. The event log may say more.")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "Retry from this stage" }));
    const dialog = await screen.findByRole("dialog", { name: "Run again from a stage" });
    expect(
      (within(dialog).getByRole("radio", { name: /Method/ }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("is not offered while the run is still going", async () => {
    api.run = runDetailOut({ status: "running", stages: [stageRunOut("literature", "running")] });
    renderRunPage();
    await waitForRun();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeTruthy();
  });
});

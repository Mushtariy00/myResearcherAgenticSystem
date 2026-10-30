// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunDetail, Stage } from "@/client";
import { json, makeQueryClient, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import { stageOverviews } from "@/lib/stage-output";
import { runDetailOut, stageRunOut } from "@/lib/stage-output.fixtures";
import { buildTimeline, STAGE_ORDER } from "@/lib/timeline";
import { enMessages as messages } from "@/test/messages";
import { RetryRunDialog } from "./retry-run-dialog";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast }));

// The method stage failed after the literature stage was approved.
const run: RunDetail = runDetailOut({
  status: "failed",
  error: "stage.error",
  stages: [stageRunOut("literature", "approved"), stageRunOut("method", "failed")],
});
const timeline = stageOverviews(buildTimeline(STAGE_ORDER, run.stages, run.status));
const STAGES: Stage[] = ["literature", "method"];

let answer: () => Response = () => json(202, { status: "accepted" });
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  answer = () => json(202, { status: "accepted" });
  fetchMock = mockApi((request, path) =>
    request.method === "POST" && path === `/api/v1/runs/${run.id}/retry`
      ? answer()
      : json(200, run),
  );
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderDialog() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Asia/Seoul">
        <RetryRunDialog run={run} stages={STAGES} timeline={timeline} />
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

const retries = () => requestsOf(fetchMock).filter((request) => request.startsWith("POST"));

describe("RetryRunDialog", () => {
  it("explains what a retry does and restarts the run from the chosen stage", async () => {
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Retry…" }));
    const dialog = await screen.findByRole("dialog", { name: "Retry this run" });

    // Where the run stopped is chosen first, and what starts over is spelled out.
    const method = within(dialog).getByRole("radio", { name: "Method" });
    expect(method.getAttribute("aria-checked")).toBe("true");
    expect(within(dialog).getAllByRole("radio")).toHaveLength(2);
    expect(dialog.textContent).toContain(
      "These stages start over, and their current outputs become outdated: Method, Coding, Experiment, and Writing.",
    );
    expect(dialog.textContent).toContain("Approved outputs of earlier stages are kept.");

    fireEvent.click(within(dialog).getByRole("radio", { name: "Literature" }));
    expect(dialog.textContent).toContain(
      "outdated: Literature, Method, Coding, Experiment, and Writing.",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry from Literature" }));

    await waitFor(() =>
      expect(retries()).toEqual([`POST /api/v1/runs/${run.id}/retry?stage=literature`]),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Retrying from Literature."));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("keeps the dialog open with the reason when the retry is refused", async () => {
    answer = () => json(409, { detail: "run.not_retryable" });
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Retry…" }));
    const dialog = await screen.findByRole("dialog", { name: "Retry this run" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry from Method" }));

    expect(
      await within(dialog).findByText("This run is still in progress, so it can't be retried yet."),
    ).toBeTruthy();
    expect(retries()).toEqual([`POST /api/v1/runs/${run.id}/retry?stage=method`]);
    expect(toast.success).not.toHaveBeenCalled();

    // Opening it again starts without the old failure.
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Retry…" }));
    const again = await screen.findByRole("dialog", { name: "Retry this run" });
    expect(within(again).queryByText(/can't be retried yet/)).toBeNull();
  });

  it("asks for a stage when the run did not stop at one", async () => {
    const completed = runDetailOut({
      status: "completed",
      stages: STAGE_ORDER.map((stage) => stageRunOut(stage, "approved")),
    });
    render(
      <QueryClientProvider client={makeQueryClient()}>
        <NextIntlClientProvider locale="en" messages={messages} timeZone="Asia/Seoul">
          <RetryRunDialog
            run={completed}
            stages={[...STAGE_ORDER]}
            timeline={stageOverviews(
              buildTimeline(STAGE_ORDER, completed.stages, completed.status),
            )}
          />
        </NextIntlClientProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry…" }));
    const dialog = await screen.findByRole("dialog", { name: "Retry this run" });
    expect(within(dialog).getByText("Choose the stage to start from.")).toBeTruthy();
    const confirm = within(dialog).getByRole("button", { name: "Retry" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole("radio", { name: "Writing" }));
    expect(
      (within(dialog).getByRole("button", { name: "Retry from Writing" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });
});

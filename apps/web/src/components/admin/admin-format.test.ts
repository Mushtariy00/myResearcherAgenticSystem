import { describe, expect, it } from "vitest";
import type { LabBalanceOut, RoutedModelOut } from "@/client";
import { balanceGauge, balanceState, movedOnePlace, pickableModels } from "./admin-format";

function model(id: string, free = false): RoutedModelOut {
  return {
    id,
    free,
    in_catalog: true,
    context_length: 1000,
    prompt_usd_per_mtok: "1",
    completion_usd_per_mtok: "2",
  };
}

const BALANCE: LabBalanceOut = {
  balance_usd: "30",
  free_tier: false,
  month: "2026-11",
  spent_this_month_usd: "10",
  free_daily_limit: 1000,
  free_calls_today: 0,
  auto_top_up: false,
  alert_floor_usd: "2",
  below_floor: false,
  checked_at: "2026-11-04T09:00:00Z",
  demo: false,
};

describe("movedOnePlace", () => {
  it("swaps a model with its neighbour", () => {
    expect(movedOnePlace(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(movedOnePlace(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
  });

  it("leaves the list alone past either end", () => {
    expect(movedOnePlace(["a", "b"], 0, -1)).toEqual(["a", "b"]);
    expect(movedOnePlace(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });
});

describe("pickableModels", () => {
  const catalog = [
    model("anthropic/claude-sonnet-4.5"),
    model("google/gemini-2.5-flash"),
    model("google/gemma-4-31b-it:free", true),
    model("meta/llama-4:free", true),
  ];
  const ids = (found: RoutedModelOut[]) => found.map((item) => item.id);

  it("offers only the chain's kind of model, and none it already has", () => {
    const paid = pickableModels(catalog, {
      free: false,
      chosen: ["google/gemini-2.5-flash"],
      query: "",
    });
    expect(ids(paid)).toEqual(["anthropic/claude-sonnet-4.5"]);
    const free = pickableModels(catalog, { free: true, chosen: [], query: "" });
    expect(ids(free)).toEqual(["google/gemma-4-31b-it:free", "meta/llama-4:free"]);
  });

  it("matches every word typed, in any case and order", () => {
    const search = (query: string) =>
      ids(pickableModels(catalog, { free: false, chosen: [], query }));
    expect(search("  FLASH  google ")).toEqual(["google/gemini-2.5-flash"]);
    expect(search("gemini sonnet")).toEqual([]);
  });
});

describe("the balance", () => {
  it("has a gauge only when there is an amount to show", () => {
    expect(balanceState(BALANCE)).toBe("known");
    expect(balanceGauge(BALANCE)).toMatchObject({ balance: 30, funds: 40, share: 0.75 });

    const freeTier = { ...BALANCE, balance_usd: "0", free_tier: true };
    expect(balanceState(freeTier)).toBe("free_tier");
    expect(balanceGauge(freeTier)).toBeNull();

    const unread = { ...BALANCE, balance_usd: null, checked_at: null };
    expect(balanceState(unread)).toBe("not_read");
    expect(balanceGauge(unread)).toBeNull();

    const unreported = { ...BALANCE, balance_usd: null };
    expect(balanceState(unreported)).toBe("not_reported");
    expect(balanceGauge(unreported)).toBeNull();
  });

  it("colours the gauge by the distance to the alert floor", () => {
    expect(balanceGauge(BALANCE)?.tone).toBe("success");
    expect(balanceGauge({ ...BALANCE, balance_usd: "3" })?.tone).toBe("warning");
    expect(balanceGauge({ ...BALANCE, balance_usd: "1", below_floor: true })?.tone).toBe("danger");
  });
});

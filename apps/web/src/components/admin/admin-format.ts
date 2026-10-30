import type { BudgetOut, LabBalanceOut, RoutedModelOut } from "@/client";
import { percentUsed, toAmount, USD } from "@/lib/format";

/**
 * Numbers of the admin views, computed the same way in both interfaces: budget use, model
 * prices and context, and how full the lab's balance and free quota are.
 */

export type UsageTone = "success" | "warning" | "danger";

/** How much of a monthly budget is used (no budget row means a $0 budget). */
export function budgetUse(budget: BudgetOut | undefined) {
  const monthly = toAmount(budget?.monthly_usd);
  const spent = toAmount(budget?.spent_usd);
  const percent = percentUsed(spent, monthly);
  const tone: UsageTone = percent >= 100 ? "danger" : percent >= 80 ? "warning" : "success";
  return { monthly, spent, percent, tone };
}

/** Model prices per million tokens: cents matter, and some cost fractions of a cent. */
export const PRICE = { ...USD, minimumFractionDigits: 2, maximumFractionDigits: 4 } as const;

/** Context windows read best as "1M" or "131K" (or "105만" in Korean). */
export const COMPACT = { notation: "compact", maximumFractionDigits: 0 } as const;

export type ModelPricing =
  | { kind: "free" }
  | { kind: "unknown" }
  | { kind: "paid"; prompt: number; completion: number };

/** What a routed model costs, as far as the catalog knows. */
export function modelPricing(model: RoutedModelOut): ModelPricing {
  if (model.free) {
    return { kind: "free" };
  }
  if (
    !model.in_catalog ||
    model.prompt_usd_per_mtok === null ||
    model.completion_usd_per_mtok === null
  ) {
    return { kind: "unknown" };
  }
  return {
    kind: "paid",
    prompt: toAmount(model.prompt_usd_per_mtok),
    completion: toAmount(model.completion_usd_per_mtok),
  };
}

/** A model chain with a React key per model: its id, counted when a chain names it twice. */
export function keyedChain<Model extends { id: string }>(
  models: readonly Model[],
): { key: string; model: Model }[] {
  const seen = new Map<string, number>();
  return models.map((model) => {
    const count = seen.get(model.id) ?? 0;
    seen.set(model.id, count + 1);
    return { key: count === 0 ? model.id : `${model.id}#${count}`, model };
  });
}

export type BalanceGaugeValue = {
  balance: number;
  spent: number;
  floor: number;
  /** Everything the lab had this month: what is left plus what was spent (top-ups included). */
  funds: number;
  /** Share of this month's funds still left, 0..1. */
  share: number;
  /** Where the alert floor sits on the same scale, 0..1. */
  floorShare: number;
  tone: UsageTone;
};

/** The balance gauge: how much of this month's funds is left, and how close the floor is. */
export function balanceGauge(data: LabBalanceOut): BalanceGaugeValue {
  const balance = Math.max(0, toAmount(data.balance_usd));
  const spent = Math.max(0, toAmount(data.spent_this_month_usd));
  const floor = Math.max(0, toAmount(data.alert_floor_usd));
  const funds = balance + spent;
  const share = funds > 0 ? Math.min(1, balance / funds) : 0;
  const floorShare = funds > 0 ? Math.min(1, floor / funds) : 0;
  const tone: UsageTone =
    data.below_floor || balance < floor ? "danger" : balance < floor * 2 ? "warning" : "success";
  return { balance, spent, floor, funds, share, floorShare, tone };
}

export type FreeQuota = {
  used: number;
  /** null: the lab has no daily limit. */
  limit: number | null;
  /** Share of the limit used, 0..100 (0 without a limit). */
  percent: number;
  tone: UsageTone;
};

/** Free-model calls today against the lab's daily limit. */
export function freeQuota(data: LabBalanceOut): FreeQuota {
  const used = Math.max(0, data.free_calls_today);
  const limit = data.free_daily_limit > 0 ? data.free_daily_limit : null;
  const percent = limit ? Math.min(100, (used / limit) * 100) : 0;
  const tone: UsageTone = percent >= 100 ? "danger" : percent >= 80 ? "warning" : "success";
  return { used, limit, percent, tone };
}

/** "2026-10" as a Date in the middle of that UTC month (safe from time-zone shifts). */
export function monthDate(month: string): Date | null {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) {
    return null;
  }
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 15));
}

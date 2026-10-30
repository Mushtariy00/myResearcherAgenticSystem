"use client";

import type { UsageModelOut, UsageOut } from "@/client";
import { useUsage } from "@/hooks/use-usage";
import { percentUsed, toAmount } from "@/lib/format";

/** The window of the profile's usage figures, in days. */
export const PROFILE_USAGE_DAYS = 30;

export type MyUsage = {
  month: string;
  budget: number;
  spent: number;
  remaining: number;
  /** Share of the budget used, 0..100. */
  percent: number;
  tone: "success" | "warning" | "danger";
  paidUsd: number;
  paidCalls: number;
  freeCalls: number;
  tokens: number;
  /** The models with the most spend, then the most calls (at most three). */
  topModels: UsageModelOut[];
  demo: boolean;
};

/** The figures the profile pages show, from GET /api/v1/usage?scope=me. */
export function myUsage(data: UsageOut): MyUsage {
  const budget = toAmount(data.budget.monthly_usd);
  const spent = toAmount(data.budget.spent_usd);
  const percent = percentUsed(spent, budget);
  const topModels = [...data.by_model]
    .sort(
      (a, b) =>
        toAmount(b.paid_usd) - toAmount(a.paid_usd) ||
        b.paid_calls + b.free_calls - (a.paid_calls + a.free_calls),
    )
    .filter((model) => model.paid_calls + model.free_calls > 0)
    .slice(0, 3);
  return {
    month: data.budget.month,
    budget,
    spent,
    remaining: Math.max(0, toAmount(data.budget.remaining_usd)),
    percent,
    tone: percent >= 100 ? "danger" : percent >= 80 ? "warning" : "success",
    paidUsd: toAmount(data.totals.paid_usd),
    paidCalls: data.totals.paid_calls,
    freeCalls: data.totals.free_calls,
    tokens: data.totals.prompt_tokens + data.totals.completion_tokens,
    topModels,
    demo: data.demo,
  };
}

/** The signed-in user's own budget and LLM use over the last 30 days (both interfaces). */
export function useMyUsage() {
  const usage = useUsage("me", PROFILE_USAGE_DAYS);
  return { query: usage, figures: usage.data ? myUsage(usage.data) : null };
}

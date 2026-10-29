import type { Decision, RunStatus } from "@/client";
import { STAGE_ORDER } from "./timeline";

const RUN_STATUSES: readonly string[] = [
  "queued",
  "running",
  "awaiting_approval",
  "completed",
  "rejected",
  "failed",
  "cancelled",
  "paused_budget",
] satisfies readonly RunStatus[];

const DECISIONS: readonly string[] = [
  "approve",
  "request_changes",
  "reject",
] satisfies readonly Decision[];

export type KnownStage = (typeof STAGE_ORDER)[number];

export function isRunStatus(value: string): value is RunStatus {
  return RUN_STATUSES.includes(value);
}

export function isDecision(value: string): value is Decision {
  return DECISIONS.includes(value);
}

export function isKnownStage(value: string): value is KnownStage {
  return (STAGE_ORDER as readonly string[]).includes(value);
}

export function isLlmTier(value: string): value is "paid" | "free" {
  return value === "paid" || value === "free";
}

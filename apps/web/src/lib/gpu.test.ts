import { describe, expect, it } from "vitest";
import type { GpuOut } from "@/client";
import { gpuReadings } from "./gpu";

const GPU: GpuOut = {
  name: "GTX 1060 6GB",
  memory_total_mb: 6144,
  memory_used_mb: 2048,
  utilization_percent: null,
  temperature_c: 61,
  power_draw_w: null,
  power_limit_w: null,
  fan_percent: null,
  sampled_at: "2026-10-30T01:00:00Z",
  demo: false,
};

describe("gpuReadings", () => {
  it("shows the executor's readings while it runs, even those with gaps", () => {
    expect(gpuReadings({ gpu: GPU, executor_alive: true, demo: false })).toBe("live");
  });

  it("says the executor is not running instead of showing a reading it left behind", () => {
    expect(gpuReadings({ gpu: GPU, executor_alive: false, demo: false })).toBe("offline");
    expect(gpuReadings({ gpu: null, executor_alive: false, demo: false })).toBe("offline");
  });

  it("waits for the first reading of an executor that runs", () => {
    expect(gpuReadings({ gpu: null, executor_alive: true, demo: false })).toBe("none");
  });

  it("shows a demo queue's generated readings, which no executor reports", () => {
    expect(gpuReadings({ gpu: { ...GPU, demo: true }, executor_alive: false, demo: true })).toBe(
      "live",
    );
    expect(gpuReadings({ gpu: null, executor_alive: false, demo: true })).toBe("none");
  });
});

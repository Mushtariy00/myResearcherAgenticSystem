import { describe, expect, it } from "vitest";
import {
  ApiError,
  errorMessageKey,
  isKnownDegradedReason,
  isKnownErrorCode,
  runErrorKey,
  toApiError,
} from "./api-error";
import { authErrorKey } from "./auth-errors";

describe("toApiError", () => {
  it("keeps the API's message code and status", () => {
    const error = toApiError({ detail: "approval.stale" }, 409);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "approval.stale", status: 409 });
  });

  it("maps FastAPI validation errors (a list of problems) to one code", () => {
    const error = toApiError({ detail: [{ loc: ["body", "topic"], msg: "too short" }] }, 422);
    expect(error.code).toBe("validation.failed");
  });

  it("treats a failed fetch (no response) as a network error", () => {
    expect(toApiError(new TypeError("Failed to fetch")).code).toBe("network.error");
  });

  it("does not trust free text in detail as a code", () => {
    expect(toApiError({ detail: "<b>oops</b>" }, 400).code).toBe("unknown");
    expect(toApiError("Bad Gateway", 502).code).toBe("server.error");
  });

  it("passes ApiError through unchanged", () => {
    const original = new ApiError("run.not_found", 404);
    expect(toApiError(original)).toBe(original);
  });
});

describe("errorMessageKey", () => {
  it("returns known codes as message keys", () => {
    expect(errorMessageKey(new ApiError("approval.duplicate", 409))).toBe("approval.duplicate");
    expect(errorMessageKey(new ApiError("permission.denied", 403))).toBe("permission.denied");
  });

  it("falls back for codes the UI does not know yet", () => {
    expect(errorMessageKey(new ApiError("gpu.queue_full", 409))).toBe("unknown");
    expect(errorMessageKey(new ApiError("gpu.exploded", 500))).toBe("server.error");
  });
});

describe("isKnownErrorCode", () => {
  it("recognises run error codes stored by the API", () => {
    expect(isKnownErrorCode("orchestrator.unavailable")).toBe(true);
    expect(isKnownErrorCode("Traceback (most recent call last)")).toBe(false);
    expect(isKnownErrorCode(null)).toBe(false);
  });
});

describe("runErrorKey", () => {
  it("translates worker codes, including per-stage schema failures", () => {
    expect(runErrorKey("stage.error")).toBe("stage.error");
    expect(runErrorKey("approval.expired")).toBe("approval.expired");
    expect(runErrorKey("method.invalid_output")).toBe("stage.invalid_output");
    expect(runErrorKey("literature.invalid_output")).toBe("stage.invalid_output");
  });

  it("leaves anything else to be shown as plain text", () => {
    expect(runErrorKey("crewai.kickoff_returned_coroutine")).toBeNull();
    expect(runErrorKey("<script>.invalid_output")).toBeNull();
    expect(runErrorKey(undefined)).toBeNull();
  });
});

describe("isKnownDegradedReason", () => {
  it("knows the placeholder reasons the worker reports", () => {
    expect(isKnownDegradedReason("stage.placeholder")).toBe(true);
    expect(isKnownDegradedReason("literature.search_pending")).toBe(true);
    expect(isKnownDegradedReason("model said so")).toBe(false);
  });
});

describe("authErrorKey", () => {
  it("maps Better Auth errors to translated keys", () => {
    expect(authErrorKey({ code: "INVALID_EMAIL_OR_PASSWORD", status: 401 })).toBe(
      "INVALID_EMAIL_OR_PASSWORD",
    );
    expect(authErrorKey({ status: 429 })).toBe("TOO_MANY_REQUESTS");
    expect(authErrorKey({ code: "SOMETHING_NEW" })).toBe("UNKNOWN");
    expect(authErrorKey(null)).toBe("UNKNOWN");
  });
});

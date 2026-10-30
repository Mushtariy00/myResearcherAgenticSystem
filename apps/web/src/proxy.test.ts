import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { proxy } from "./proxy";

function nonceOf(policy: string | null): string | undefined {
  return policy?.match(/'nonce-([^']+)'/)?.[1];
}

describe("proxy", () => {
  it("gives every page a Content-Security-Policy with a fresh nonce for the renderer", () => {
    const first = proxy(new NextRequest("http://localhost:8080/login"));
    const second = proxy(new NextRequest("http://localhost:8080/login"));
    const nonce = nonceOf(first.headers.get("content-security-policy"));
    expect(nonce).toBeTruthy();
    expect(nonceOf(second.headers.get("content-security-policy"))).not.toBe(nonce);
    // Next.js forwards these request headers to the renderer: it reads the nonce from the
    // policy, the root layout from x-nonce.
    expect(first.headers.get("x-middleware-request-x-nonce")).toBe(nonce);
    expect(nonceOf(first.headers.get("x-middleware-request-content-security-policy"))).toBe(nonce);
  });

  it("sends a signed-out visitor of a protected page to sign in, back to the page after", () => {
    const response = proxy(new NextRequest("http://localhost:8080/runs/abc?tab=log"));
    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/runs/abc?tab=log");
  });
});

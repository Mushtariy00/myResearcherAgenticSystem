import { describe, expect, it } from "vitest";
import { contentSecurityPolicy, newNonce } from "./csp";

function directives(policy: string): Map<string, string[]> {
  return new Map(
    policy.split("; ").map((directive): [string, string[]] => {
      const [name = "", ...values] = directive.split(" ");
      return [name, values];
    }),
  );
}

describe("contentSecurityPolicy", () => {
  it("runs only scripts that carry the nonce or that such scripts load", () => {
    const script = directives(contentSecurityPolicy("abc123", false)).get("script-src");
    expect(script).toEqual(["'self'", "'nonce-abc123'", "'strict-dynamic'"]);
  });

  it("never allows inline or eval'd scripts in production", () => {
    const policy = contentSecurityPolicy("abc123", false);
    expect(directives(policy).get("script-src")).not.toContain("'unsafe-inline'");
    expect(policy).not.toContain("'unsafe-eval'");
    expect(policy).not.toContain("ws:");
  });

  it("locks down plugins, base URLs, form targets and framing", () => {
    const policy = directives(contentSecurityPolicy("abc123", false));
    expect(policy.get("object-src")).toEqual(["'none'"]);
    expect(policy.get("base-uri")).toEqual(["'self'"]);
    expect(policy.get("form-action")).toEqual(["'self'"]);
    expect(policy.get("frame-ancestors")).toEqual(["'none'"]);
    expect(policy.get("connect-src")).toEqual(["'self'"]);
  });

  it("lets development use React's eval-based debugging and the hot-reload socket", () => {
    const policy = directives(contentSecurityPolicy("abc123", true));
    expect(policy.get("script-src")).toContain("'unsafe-eval'");
    expect(policy.get("connect-src")).toEqual(["'self'", "ws:"]);
  });
});

describe("newNonce", () => {
  it("is different every time and safe inside the header", () => {
    const first = newNonce();
    expect(first).not.toBe(newNonce());
    expect(first).toMatch(/^[A-Za-z0-9+/]+=*$/);
    expect(first.length).toBeGreaterThanOrEqual(24);
  });
});

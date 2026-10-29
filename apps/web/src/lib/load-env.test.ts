import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { loadRootEnv } from "./load-env";

const KEYS = [
  "AUTH_DATABASE_URL",
  "BETTER_AUTH_URL",
  "SMTP_URL",
  "MAIL_FROM",
  "ARP_OPENROUTER_API_KEY",
  "ARP_GATEWAY_TOKEN",
];

describe("loadRootEnv", () => {
  let dir: string;
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "arp-env-"));
    for (const key of KEYS) {
      saved[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
    for (const key of KEYS) {
      if (saved[key] === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = saved[key];
      }
    }
  });

  it("loads the web app's keys and never the gateway or OpenRouter secrets", () => {
    writeFileSync(
      path.join(dir, ".env"),
      [
        "AUTH_DATABASE_URL=postgres://u:p@localhost/db?options=-c%20search_path%3Dauth",
        "BETTER_AUTH_URL=http://localhost:8080",
        "SMTP_URL=smtp://127.0.0.1:1025",
        "MAIL_FROM=no-reply@arp.local",
        "ARP_OPENROUTER_API_KEY=sk-should-not-load",
        "ARP_GATEWAY_TOKEN=should-not-load",
      ].join("\n"),
    );
    loadRootEnv(dir);
    expect(process.env.AUTH_DATABASE_URL).toContain("search_path%3Dauth");
    expect(process.env.BETTER_AUTH_URL).toBe("http://localhost:8080");
    expect(process.env.SMTP_URL).toBe("smtp://127.0.0.1:1025");
    expect(process.env.MAIL_FROM).toBe("no-reply@arp.local");
    expect(process.env.ARP_OPENROUTER_API_KEY).toBeUndefined();
    expect(process.env.ARP_GATEWAY_TOKEN).toBeUndefined();
  });

  it("lets real environment variables win over the file", () => {
    process.env.BETTER_AUTH_URL = "https://arp.example";
    writeFileSync(path.join(dir, ".env"), "BETTER_AUTH_URL=http://localhost:8080\n");
    loadRootEnv(dir);
    expect(process.env.BETTER_AUTH_URL).toBe("https://arp.example");
  });

  it("is a no-op without a .env file", () => {
    expect(() => loadRootEnv(dir)).not.toThrow();
    expect(process.env.AUTH_DATABASE_URL).toBeUndefined();
  });
});

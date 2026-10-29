import { readFileSync } from "node:fs";
import path from "node:path";
import { parseEnv } from "node:util";

/**
 * Keys the web app reads from the repo-root `.env` (shared with the Python services).
 * Only these are copied, so the gateway token and the OpenRouter key never enter this process.
 */
const WEB_ENV_KEY =
  /^(BETTER_AUTH_[A-Z0-9_]+|AUTH_DATABASE_URL|SMTP_URL|MAIL_FROM|NEXT_PUBLIC_[A-Z0-9_]+)$/;

/**
 * Copies the web app's keys from `<rootDir>/.env` into `process.env`. Variables that are already
 * set win, and a missing file is fine (containers get real environment variables).
 */
export function loadRootEnv(rootDir: string): void {
  let text: string;
  try {
    text = readFileSync(path.join(rootDir, ".env"), "utf8");
  } catch {
    return;
  }
  for (const [key, value] of Object.entries(parseEnv(text))) {
    if (WEB_ENV_KEY.test(key) && process.env[key] === undefined && typeof value === "string") {
      process.env[key] = value;
    }
  }
}

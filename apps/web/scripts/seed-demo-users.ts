/**
 * Creates the demo accounts that `make demo-seed` fills with projects and runs. Idempotent:
 * accounts that already exist are left as they are (passwords included).
 *
 *   pnpm --filter @agentic/web exec node scripts/seed-demo-users.ts
 *
 * Every demo account gets the same password: DEMO_USER_PASSWORD when it is set, otherwise one
 * generated on the first run and saved to .data/demo-users.env (mode 600). It is never printed.
 * Accounts are created through Better Auth's server API, like scripts/bootstrap-admin.ts.
 * Runs on Node's built-in TypeScript support (no build step).
 */
import { randomBytes } from "node:crypto";
import { chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { parseEnv } from "node:util";
import { auth, authDbPool, MIN_PASSWORD_LENGTH } from "../src/lib/auth.ts";

// Keep in sync with DEMO_ACCOUNTS in apps/worker/src/agentic_worker/seed_demo.py.
const DEMO_USERS = [
  { email: "demo-admin@lab.test", name: "Demo Admin", role: "admin" },
  { email: "jiwoo.park@lab.test", name: "Ji-woo Park", role: "user" },
  { email: "dilnoza.karimova@lab.test", name: "Dilnoza Karimova", role: "user" },
  { email: "mateo.silva@lab.test", name: "Mateo Silva", role: "user" },
] as const;

const PASSWORD_KEY = "DEMO_USER_PASSWORD";
// pnpm runs package scripts from apps/web; the repo root holds .data (git-ignored).
const ROOT = path.resolve(process.cwd(), "../..");
const PASSWORD_FILE = path.join(ROOT, ".data", "demo-users.env");

function fail(message: string): never {
  console.error(`seed-demo-users: ${message}`);
  process.exit(1);
}

function errorCode(error: unknown): string {
  if (error && typeof error === "object" && "body" in error) {
    const body = (error as { body?: { code?: string; message?: string } }).body;
    if (body?.code || body?.message) {
      return body.code ?? body.message ?? "";
    }
  }
  return error instanceof Error ? error.message : String(error);
}

function savedPassword(): string | undefined {
  let text: string;
  try {
    text = readFileSync(PASSWORD_FILE, "utf8");
  } catch {
    return undefined; // first run
  }
  const value = parseEnv(text)[PASSWORD_KEY];
  return typeof value === "string" && value ? value : undefined;
}

/** The shared password and where it lives (never the password itself in any output). */
function demoPassword(): { password: string; source: string } {
  const fromEnvironment = process.env[PASSWORD_KEY];
  if (fromEnvironment) {
    return { password: fromEnvironment, source: `the ${PASSWORD_KEY} variable` };
  }
  const source = path.relative(ROOT, PASSWORD_FILE);
  const saved = savedPassword();
  if (saved) {
    return { password: saved, source };
  }
  const generated = randomBytes(18).toString("base64url"); // 24 characters
  mkdirSync(path.dirname(PASSWORD_FILE), { recursive: true, mode: 0o700 });
  const header = "# Password of the demo accounts created by make demo-seed. Keep it private.";
  writeFileSync(PASSWORD_FILE, `${header}\n${PASSWORD_KEY}=${generated}\n`, { mode: 0o600 });
  chmodSync(PASSWORD_FILE, 0o600); // also when an older file had wider permissions
  return { password: generated, source };
}

async function main(): Promise<void> {
  const { password, source } = demoPassword();
  if (password.length < MIN_PASSWORD_LENGTH) {
    fail(`${PASSWORD_KEY} must have at least ${MIN_PASSWORD_LENGTH} characters`);
  }
  const context = await auth.$context;
  for (const user of DEMO_USERS) {
    if (await context.internalAdapter.findUserByEmail(user.email)) {
      console.log(`exists   ${user.email}`);
      continue;
    }
    try {
      // Server-side call without request headers, as in bootstrap-admin.ts.
      const { user: created } = await auth.api.createUser({
        body: {
          email: user.email,
          name: user.name,
          password,
          role: user.role,
          data: { emailVerified: true },
        },
      });
      console.log(`created  ${created.email} (${user.role})`);
    } catch (error) {
      fail(`could not create ${user.email}: ${errorCode(error)}`);
    }
  }
  console.log(`Demo accounts are ready. Their password is in ${source}.`);
}

try {
  await main();
} finally {
  await authDbPool.end();
}

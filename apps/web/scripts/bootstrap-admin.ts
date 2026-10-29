/**
 * Creates the FIRST lab admin straight in the auth database. There is no public sign-up page.
 *
 *   pnpm --filter @agentic/web bootstrap-admin -- --email you@lab.example --name "Your Name" \
 *     --password '<at least 12 characters>'
 *
 * The password may come from BOOTSTRAP_ADMIN_PASSWORD instead, which keeps it out of shell
 * history. Refuses to run when an admin already exists, unless --force is passed.
 * Runs on Node's built-in TypeScript support (no build step).
 */
import { parseArgs } from "node:util";
import { auth, authDbPool, MIN_PASSWORD_LENGTH } from "../src/lib/auth.ts";

const USAGE =
  "usage: bootstrap-admin --email <email> --name <name> [--password <password>] [--force]\n" +
  "       (or set BOOTSTRAP_ADMIN_PASSWORD instead of --password)";

function fail(message: string): never {
  console.error(`bootstrap-admin: ${message}`);
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

async function main(): Promise<void> {
  const { values } = parseArgs({
    // `pnpm run x -- --flag` may pass the separator through; it is not a positional here.
    args: process.argv.slice(2).filter((arg) => arg !== "--"),
    options: {
      email: { type: "string" },
      name: { type: "string" },
      password: { type: "string" },
      force: { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false },
    },
    strict: true,
  });
  if (values.help) {
    console.log(USAGE);
    return;
  }

  const email = values.email?.trim().toLowerCase();
  const name = values.name?.trim();
  const password = values.password ?? process.env.BOOTSTRAP_ADMIN_PASSWORD;
  if (!email || !name || !password) {
    fail(`--email, --name and a password are required\n${USAGE}`);
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    fail(`the password must have at least ${MIN_PASSWORD_LENGTH} characters`);
  }

  const context = await auth.$context;
  if (await context.internalAdapter.findUserByEmail(email)) {
    fail(`a user with the email ${email} already exists`);
  }
  const admins = await context.adapter.count({
    model: "user",
    where: [{ field: "role", value: "admin" }],
  });
  if (admins > 0 && !values.force) {
    fail(
      `${admins} admin account(s) already exist. Invite people from the admin page instead, or pass --force.`,
    );
  }

  try {
    // Server-side call without request headers: allowed by the admin plugin for bootstrapping.
    const { user } = await auth.api.createUser({
      body: { email, name, password, role: "admin", data: { emailVerified: true } },
    });
    console.log(
      `Created admin ${user.email} (id ${user.id}). Sign in at ${process.env.BETTER_AUTH_URL ?? "/"}/login`,
    );
  } catch (error) {
    fail(`could not create the admin: ${errorCode(error)}`);
  }
}

try {
  await main();
} finally {
  await authDbPool.end();
}

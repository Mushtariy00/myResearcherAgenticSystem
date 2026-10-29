import { hash, verify } from "@node-rs/argon2";

// argon2id (the library default) with the OWASP baseline: 19 MiB memory, 2 passes, 1 lane.
const ARGON2_OPTIONS = { memoryCost: 19_456, timeCost: 2, parallelism: 1 };

export function hashPassword(password: string): Promise<string> {
  return hash(password, ARGON2_OPTIONS);
}

export async function verifyPassword(data: { hash: string; password: string }): Promise<boolean> {
  try {
    return await verify(data.hash, data.password);
  } catch {
    return false; // malformed or foreign hash
  }
}

import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import ko from "../../messages/ko.json";
import { KNOWN_DEGRADED_REASONS, KNOWN_ERROR_CODES } from "./api-error";
import { AUTH_ERROR_CODES } from "./auth-errors";

type Tree = { [key: string]: string | Tree };

function leafKeys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string" ? [`${prefix}${key}`] : leafKeys(value, `${prefix}${key}.`),
  );
}

function lookup(tree: Tree, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => (node as Tree | undefined)?.[key], tree);
}

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort();

describe("messages", () => {
  it("has the same keys in English and Korean", () => {
    expect(leafKeys(ko as Tree).sort()).toEqual(leafKeys(en as Tree).sort());
  });

  it("uses the same placeholders in both languages", () => {
    for (const key of leafKeys(en as Tree)) {
      const english = lookup(en as Tree, key) as string;
      const korean = lookup(ko as Tree, key) as string;
      expect(placeholders(korean), key).toEqual(placeholders(english));
    }
  });

  it("translates every API error code the UI can show", () => {
    for (const code of KNOWN_ERROR_CODES) {
      expect(typeof lookup(en as Tree, `errors.${code}`), code).toBe("string");
      expect(typeof lookup(ko as Tree, `errors.${code}`), code).toBe("string");
    }
  });

  it("translates every known degraded-output reason", () => {
    for (const reason of KNOWN_DEGRADED_REASONS) {
      expect(typeof lookup(en as Tree, `degradedReasons.${reason}`), reason).toBe("string");
      expect(typeof lookup(ko as Tree, `degradedReasons.${reason}`), reason).toBe("string");
    }
  });

  it("translates every Better Auth error code the UI can show", () => {
    for (const code of AUTH_ERROR_CODES) {
      expect(typeof lookup(en as Tree, `auth.errors.${code}`), code).toBe("string");
      expect(typeof lookup(ko as Tree, `auth.errors.${code}`), code).toBe("string");
    }
  });
});

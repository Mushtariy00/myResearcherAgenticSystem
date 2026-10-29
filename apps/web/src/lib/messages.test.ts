import { describe, expect, it } from "vitest";
import { MESSAGE_AREAS } from "@/i18n/messages";
import { enMessages as en, koMessages as ko, messageFiles } from "@/test/messages";
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
  it("has exactly the registered area files in every locale", () => {
    for (const locale of ["en", "ko"]) {
      expect(Object.keys(messageFiles[locale] ?? {}).sort(), locale).toEqual(
        [...MESSAGE_AREAS].sort(),
      );
    }
  });

  it("keeps each top-level namespace in one area file", () => {
    for (const [locale, areas] of Object.entries(messageFiles)) {
      const owner = new Map<string, string>();
      for (const [area, content] of Object.entries(areas)) {
        for (const namespace of Object.keys(content)) {
          expect(owner.get(namespace), `${locale}: ${namespace} in ${area}`).toBeUndefined();
          owner.set(namespace, area);
        }
      }
    }
  });

  it("has the same keys in English and Korean", () => {
    expect(leafKeys(ko).sort()).toEqual(leafKeys(en).sort());
  });

  it("uses the same placeholders in both languages", () => {
    for (const key of leafKeys(en)) {
      const english = lookup(en, key) as string;
      const korean = lookup(ko, key) as string;
      expect(placeholders(korean), key).toEqual(placeholders(english));
    }
  });

  it("translates every API error code the UI can show", () => {
    for (const code of KNOWN_ERROR_CODES) {
      expect(typeof lookup(en, `errors.${code}`), code).toBe("string");
      expect(typeof lookup(ko, `errors.${code}`), code).toBe("string");
    }
  });

  it("translates every known degraded-output reason", () => {
    for (const reason of KNOWN_DEGRADED_REASONS) {
      expect(typeof lookup(en, `degradedReasons.${reason}`), reason).toBe("string");
      expect(typeof lookup(ko, `degradedReasons.${reason}`), reason).toBe("string");
    }
  });

  it("translates every Better Auth error code the UI can show", () => {
    for (const code of AUTH_ERROR_CODES) {
      expect(typeof lookup(en, `auth.errors.${code}`), code).toBe("string");
      expect(typeof lookup(ko, `auth.errors.${code}`), code).toBe("string");
    }
  });
});

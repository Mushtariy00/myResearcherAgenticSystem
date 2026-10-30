import { describe, expect, it } from "vitest";
import {
  PROJECT_SETTINGS_ERROR_CODES,
  projectSettingsFieldError,
} from "@/hooks/use-project-settings";
import { NEW_RUN_ERROR_CODES, newRunFieldError } from "@/lib/new-run-schema";
import { enMessages, koMessages } from "@/test/messages";

type Tree = { [key: string]: string | Tree };

function lookup(tree: Tree, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => (node as Tree | undefined)?.[key], tree);
}

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)/g)].map((match) => match[1]);

/** Each message exists in both languages and asks only for values the hook passes along. */
function expectMessage(key: string, values: Record<string, number>) {
  for (const [locale, messages] of [
    ["en", enMessages],
    ["ko", koMessages],
  ] as const) {
    const text = lookup(messages, key);
    expect(typeof text, `${locale}: ${key}`).toBe("string");
    for (const name of placeholders(text as string)) {
      expect(Object.keys(values), `${locale}: ${key} uses {${name}}`).toContain(name);
    }
  }
}

describe("field error messages", () => {
  it("exist for every new-run error code", () => {
    for (const code of NEW_RUN_ERROR_CODES) {
      const message = newRunFieldError({ message: code });
      expect(message?.code).toBe(code);
      expectMessage(message?.key ?? "", message?.values ?? {});
    }
  });

  it("exist for every project settings error code", () => {
    for (const code of PROJECT_SETTINGS_ERROR_CODES) {
      const message = projectSettingsFieldError({ message: code });
      expect(message?.code).toBe(code);
      expectMessage(message?.key ?? "", message?.values ?? {});
    }
  });
});

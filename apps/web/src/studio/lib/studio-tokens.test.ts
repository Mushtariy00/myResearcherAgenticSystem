import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrast, distance, over, parseOklch, type Rgba, withAlpha } from "@/studio/test/color";

/**
 * The Studio tokens in globals.css, checked the way a browser paints them: text keeps 4.5:1 on
 * every surface it sits on (no opacity tricks; see the pipeline graph's stepped-back nodes) and
 * hover fills differ visibly from what they replace.
 */
const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");

function declarations(selector: string): Map<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) {
    throw new Error(`globals.css has no "${selector}" block`);
  }
  const body = css.slice(start, css.indexOf("\n}", start));
  return new Map(
    Array.from(body.matchAll(/--([\w-]+):\s*([^;]+);/g), (match) => [
      match[1] ?? "",
      (match[2] ?? "").trim(),
    ]),
  );
}

const LIGHT = declarations('[data-ui="studio"]');
const DARK = declarations('[data-ui="studio"].dark');

type Theme = "light" | "dark";

function token(theme: Theme, name: string): Rgba {
  // Dark mode redefines what it changes; everything else cascades from the light block.
  const value = (theme === "dark" ? DARK.get(name) : undefined) ?? LIGHT.get(name);
  if (!value) {
    throw new Error(`--${name} is not defined for ${theme}`);
  }
  return parseOklch(value);
}

const TEXT = [
  "foreground",
  "muted-foreground",
  "studio-accent-fg",
  "studio-neutral-fg",
  "studio-info-fg",
  "studio-success-fg",
  "studio-warning-fg",
  "studio-danger-fg",
  "stage-literature-fg",
  "stage-method-fg",
  "stage-coding-fg",
  "stage-experiment-fg",
  "stage-writing-fg",
];

/** `data-tone` / `data-stage` fills; their text colour is `<fill>-fg`. */
const TONES = [
  "studio-neutral",
  "studio-info",
  "studio-success",
  "studio-warning",
  "studio-danger",
  "stage-literature",
  "stage-method",
  "stage-coding",
  "stage-experiment",
  "stage-writing",
];

type Surfaces = { page: Rgba; card: Rgba; glass: Rgba; "glass on glass": Rgba };

function surfaces(theme: Theme): Surfaces {
  const page = token(theme, "background");
  const glass = over(token(theme, "studio-glass"), page);
  return {
    page,
    card: token(theme, "card"),
    glass,
    // A pipeline node or a chip on a glass card.
    "glass on glass": over(token(theme, "studio-glass"), glass),
  };
}

describe.each(["light", "dark"] as const)("Studio tokens (%s)", (theme) => {
  it("keep text at 4.5:1 or more on the page, cards and glass", () => {
    for (const [surface, background] of Object.entries(surfaces(theme))) {
      for (const name of TEXT) {
        expect(
          contrast(token(theme, name), background),
          `--${name} on ${surface}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("keep pill and chip text at 4.5:1 on its own 12% tint", () => {
    for (const [surface, background] of Object.entries(surfaces(theme))) {
      for (const fill of TONES) {
        const tint = over(withAlpha(token(theme, fill), 0.12), background);
        expect(
          contrast(token(theme, `${fill}-fg`), tint),
          `--${fill}-fg on its tint, on ${surface}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("show a visible hover fill on the page, on glass, and in place of a glass fill", () => {
    const hover = token(theme, "studio-hover");
    const { page, glass, "glass on glass": glassOnGlass } = surfaces(theme);
    const visible = 0.02;
    // Ghost and icon buttons on the page or the top bar.
    expect(distance(over(hover, page), page)).toBeGreaterThanOrEqual(visible);
    // Sidebar items and the user card on the glass sidebar.
    expect(distance(over(hover, glass), glass)).toBeGreaterThanOrEqual(visible);
    // Outline buttons: the hover fill replaces their glass fill, on the page and on a card.
    expect(distance(over(hover, page), glass)).toBeGreaterThanOrEqual(visible);
    expect(distance(over(hover, glass), glassOnGlass)).toBeGreaterThanOrEqual(visible);
  });
});

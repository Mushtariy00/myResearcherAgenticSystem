import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The motion rules of the Studio block in globals.css: loops pause off screen, the aurora behind
 * working screens stands still, and display headings never overflow a phone.
 */
const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");

/** The declarations of the first rule whose selector list is exactly `selector`. */
function rule(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) {
    throw new Error(`globals.css has no "${selector}" rule`);
  }
  return css.slice(start, css.indexOf("}", start));
}

/** The off-screen pause rule: the one whose selector list ends with this selector. */
const PAUSE_LAST_SELECTOR = '[data-ui="studio"] [data-offscreen] *::after {';

/** The selector list and the body of the rule that `lastSelector` closes. */
function pauseRule(): { selectors: string[]; body: string; at: number } {
  const open = css.indexOf(PAUSE_LAST_SELECTOR) + PAUSE_LAST_SELECTOR.length - 1;
  const previous = Math.max(css.lastIndexOf("}", open), css.lastIndexOf("*/", open) + 1);
  return {
    selectors: css
      .slice(previous + 1, open)
      .split(",")
      .map((selector) => selector.trim()),
    body: css.slice(open, css.indexOf("}", open)),
    at: open,
  };
}

describe("Studio loops", () => {
  it("pause off screen: regions (data-paused) and looping effects (data-offscreen), pseudo-elements too", () => {
    const { selectors, body } = pauseRule();
    expect(body).toMatch(/animation-play-state: paused/);
    for (const marker of ['[data-paused="true"]', "[data-offscreen]"]) {
      for (const suffix of ["", "::before", "::after", " *", " *::before", " *::after"]) {
        expect(selectors, `${marker}${suffix}`).toContain(`[data-ui="studio"] ${marker}${suffix}`);
      }
    }
  });

  it("come after every loop they pause, so they win at equal specificity", () => {
    const pauseAt = pauseRule().at;
    for (const loop of [
      "animation: studio-shimmer",
      "animation: studio-skeleton",
      "animation: studio-pulse",
      "animation: studio-beam-spin",
      "animation: studio-marquee",
      "animation: studio-flow-x",
      "animation-name: var(--blob-keyframes)",
    ]) {
      const at = css.indexOf(loop);
      expect(at, loop).toBeGreaterThan(0);
      expect(at, loop).toBeLessThan(pauseAt);
    }
  });
});

describe("the Studio aurora", () => {
  it("animates only the vivid variant, with longhands the pause rules do not reset", () => {
    const blob = rule('[data-ui="studio"] .studio-aurora-blob');
    expect(blob).not.toMatch(/will-change/);
    expect(blob).not.toMatch(/animation/);
    const vivid = rule(
      '[data-ui="studio"] .studio-aurora[data-variant="vivid"] .studio-aurora-blob',
    );
    expect(vivid).toMatch(/animation-name: var\(--blob-keyframes\)/);
    expect(vivid).not.toMatch(/animation:/);
    expect(vivid).not.toMatch(/will-change/);
  });

  it("stands still with reduced motion", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduced).toContain(
      '[data-ui="studio"] .studio-aurora[data-variant] .studio-aurora-blob',
    );
  });
});

describe("Studio display headings", () => {
  it("break long words instead of overflowing a narrow screen", () => {
    expect(rule('[data-ui="studio"] .studio-display')).toMatch(/overflow-wrap: anywhere/);
  });
});

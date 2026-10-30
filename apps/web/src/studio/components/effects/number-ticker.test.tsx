// @vitest-environment jsdom
import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { USD } from "@/lib/format";
import { installDomFakes } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { NumberTicker } from "./number-ticker";

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
});

/** The copy assistive technology reads (the moving digits are hidden from it). */
function spokenValue(container: HTMLElement): string | undefined {
  return container.querySelector(".sr-only")?.textContent ?? undefined;
}

describe("NumberTicker", () => {
  it("formats with the UI language", () => {
    const english = renderStudio(<NumberTicker value={12000} format={{ notation: "compact" }} />);
    expect(spokenValue(english.container)).toBe("12K");
    english.unmount();

    const korean = renderStudio(<NumberTicker value={12000} format={{ notation: "compact" }} />, {
      locale: "ko",
    });
    expect(spokenValue(korean.container)).toBe("1.2만");
  });

  it("formats money the way the rest of the app does, in both languages", () => {
    const english = renderStudio(<NumberTicker value={1234.5} format={USD} />);
    expect(spokenValue(english.container)).toBe("$1,234.50");
    english.unmount();

    const korean = renderStudio(<NumberTicker value={1234.5} format={USD} />, { locale: "ko" });
    expect(spokenValue(korean.container)).toBe("$1,234.50");
  });

  it("uses tabular figures and reserves the final width", () => {
    const { container } = renderStudio(<NumberTicker value={98765} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain("tabular-nums");
    const [sizer, display] = Array.from(root.children) as HTMLElement[];
    expect(sizer?.className).toContain("invisible");
    expect(sizer?.textContent).toBe("98,765");
    expect(sizer?.getAttribute("aria-hidden")).toBe("true");
    expect(display?.getAttribute("aria-hidden")).toBe("true");
  });

  it("counts from `from` when it appears on the client, and lands on the value", async () => {
    // The first ticker mounts like a server-rendered one; later ones mount on the client.
    renderStudio(<NumberTicker value={1} />);
    cleanup();

    const { container } = renderStudio(<NumberTicker value={250} from={0} />);
    const display = container.querySelector('[aria-hidden="true"]:not(.invisible)');
    expect(screen.getByText("250", { selector: ".sr-only" })).toBeTruthy();
    await waitFor(() => expect(display?.textContent).toBe("250"), { timeout: 4000 });
  });

  it("counts whole numbers without decimals and lands exactly on the value", async () => {
    renderStudio(<NumberTicker value={1} />);
    cleanup();

    const { container } = renderStudio(<NumberTicker value={8} from={0} />);
    const display = container.querySelector('[aria-hidden="true"]:not(.invisible)') as HTMLElement;
    const seen = new Set<string>([display.textContent ?? ""]);
    const observer = new MutationObserver(() => seen.add(display.textContent ?? ""));
    observer.observe(display, { characterData: true, childList: true, subtree: true });
    await waitFor(() => expect(display.textContent).toBe("8"), { timeout: 4000 });
    observer.disconnect();
    for (const text of seen) {
      expect(text, text).toMatch(/^\d+$/);
    }
  });
});

/**
 * Test-only browser APIs jsdom lacks, for Studio component tests (`// @vitest-environment jsdom`).
 * `setReducedMotion` drives `matchMedia("(prefers-reduced-motion: reduce)")` and notifies
 * listeners, the way a visitor changing their system setting would.
 */
import { vi } from "vitest";

type Listener = (event: MediaQueryListEvent) => void;

const state = { reducedMotion: false, finePointer: true };
const lists = new Set<{ query: string; listeners: Set<Listener> }>();

function matches(query: string): boolean {
  if (query.includes("prefers-reduced-motion")) {
    return state.reducedMotion && !query.includes("no-preference");
  }
  if (query.includes("pointer: fine") || query.includes("hover: hover")) {
    return state.finePointer;
  }
  return false;
}

function matchMedia(query: string): MediaQueryList {
  const entry = { query, listeners: new Set<Listener>() };
  lists.add(entry);
  const list = {
    media: query,
    get matches() {
      return matches(query);
    },
    onchange: null,
    addEventListener: (_type: string, listener: Listener) => entry.listeners.add(listener),
    removeEventListener: (_type: string, listener: Listener) => entry.listeners.delete(listener),
    addListener: (listener: Listener) => entry.listeners.add(listener),
    removeListener: (listener: Listener) => entry.listeners.delete(listener),
    dispatchEvent: () => true,
  };
  return list as unknown as MediaQueryList;
}

function notify(): void {
  for (const entry of lists) {
    for (const listener of entry.listeners) {
      listener({ matches: matches(entry.query), media: entry.query } as MediaQueryListEvent);
    }
  }
}

export function setReducedMotion(reduced: boolean): void {
  state.reducedMotion = reduced;
  notify();
}

export function setFinePointer(fine: boolean): void {
  state.finePointer = fine;
  notify();
}

/** IntersectionObserver that reports every observed element as visible right away. */
class VisibleIntersectionObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0];
  private readonly callback: IntersectionObserverCallback;
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    this.callback(
      [{ isIntersecting: true, intersectionRatio: 1, target } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

/** Installs the fakes once per test file (call at the top, before rendering). */
export function installDomFakes(): void {
  vi.stubGlobal("matchMedia", matchMedia);
  Object.defineProperty(window, "matchMedia", { configurable: true, value: matchMedia });
  vi.stubGlobal("IntersectionObserver", VisibleIntersectionObserver);
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
  state.reducedMotion = false;
  state.finePointer = true;
}

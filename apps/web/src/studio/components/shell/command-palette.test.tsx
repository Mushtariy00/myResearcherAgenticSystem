// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ProjectOut } from "@/client";
import { listProjectsQueryKey } from "@/client/@tanstack/react-query.gen";
import { json, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import { setLocale } from "@/i18n/actions";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { CommandPalette, CommandPaletteContent, isPaletteShortcut } from "./command-palette";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/studio/dashboard",
}));

vi.mock("@/i18n/actions", () => ({ setLocale: vi.fn(async () => {}) }));

const PROJECTS: ProjectOut[] = [
  {
    id: "p-depth",
    name: "Monocular depth",
    description: "NYU Depth V2 baselines",
    privacy: "standard",
    allow_free_models: true,
    created_by: "user-1",
    created_at: "2026-10-01T00:00:00Z",
    my_role: "owner",
  },
  {
    id: "p-seg",
    name: "Semantic segmentation",
    description: "",
    privacy: "confidential",
    allow_free_models: false,
    created_by: "user-2",
    created_at: "2026-10-02T00:00:00Z",
    my_role: "viewer",
  },
];

function renderPalette(role: "admin" | "user" = "user") {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(listProjectsQueryKey(), PROJECTS);
  const onDone = vi.fn();
  renderStudio(<CommandPaletteContent onDone={onDone} />, {
    user: { ...TEST_USER, role },
    queryClient,
  });
  return { onDone, input: screen.getByRole("combobox") };
}

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CommandPaletteContent", () => {
  it("filters as you type and opens the chosen page", () => {
    const { input, onDone } = renderPalette();
    fireEvent.change(input, { target: { value: "pap" } });

    expect(screen.getByRole("option", { name: "Papers" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "Dashboard" })).toBeNull();

    fireEvent.keyDown(input, { key: "Enter" });
    expect(router.push).toHaveBeenCalledWith("/studio/papers");
    expect(onDone).toHaveBeenCalled();
  });

  it("finds projects by name and opens them in Studio", () => {
    const { input } = renderPalette();
    fireEvent.change(input, { target: { value: "segmentation" } });
    const option = screen.getByRole("option", { name: "Semantic segmentation" });
    expect(screen.queryByRole("option", { name: "Monocular depth" })).toBeNull();

    fireEvent.click(option);
    expect(router.push).toHaveBeenCalledWith("/studio/projects/p-seg");
  });

  it("opens the same page in Classic", () => {
    const { input } = renderPalette();
    fireEvent.change(input, { target: { value: "classic" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(router.push).toHaveBeenCalledWith("/");
  });

  it("shows Admin to lab admins only", () => {
    renderPalette("user");
    expect(screen.queryByRole("option", { name: "Admin" })).toBeNull();
    cleanup();
    renderPalette("admin");
    expect(screen.getByRole("option", { name: "Admin" })).toBeTruthy();
  });

  it("switches the language, which the user's emails then use too", async () => {
    const fetchMock = mockApi(() => json(200, { email_notifications: true, locale: "ko" }));
    const { input, onDone } = renderPalette();
    fireEvent.change(input, { target: { value: "한국어" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onDone).toHaveBeenCalled();
    await waitFor(() => expect(router.refresh).toHaveBeenCalledTimes(1));
    expect(setLocale).toHaveBeenCalledWith("ko");
    await waitFor(() => expect(requestsOf(fetchMock)).toEqual(["PUT /api/v1/me/settings"]));
  });

  it("says when nothing matches", () => {
    const { input } = renderPalette();
    fireEvent.change(input, { target: { value: "zzzzzz" } });
    expect(screen.getByText("No results")).toBeTruthy();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });
});

function PaletteHarness() {
  const [open, setOpen] = useState(false);
  return <CommandPalette open={open} onOpenChange={setOpen} />;
}

describe("CommandPalette", () => {
  it("recognises ⌘K and Ctrl+K, nothing else", () => {
    const key = (init: KeyboardEventInit) => new KeyboardEvent("keydown", init);
    expect(isPaletteShortcut(key({ key: "k", metaKey: true }))).toBe(true);
    expect(isPaletteShortcut(key({ key: "K", ctrlKey: true }))).toBe(true);
    expect(isPaletteShortcut(key({ key: "k" }))).toBe(false);
    expect(isPaletteShortcut(key({ key: "k", ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(isPaletteShortcut(key({ key: "j", ctrlKey: true }))).toBe(false);
  });

  it("finds the K key on layouts that do not type a Latin k there", () => {
    const key = (init: KeyboardEventInit) => new KeyboardEvent("keydown", init);
    // Korean 2-set, Cyrillic and an IME that is composing all report another `key`.
    expect(isPaletteShortcut(key({ key: "ㅏ", code: "KeyK", ctrlKey: true }))).toBe(true);
    expect(isPaletteShortcut(key({ key: "л", code: "KeyK", metaKey: true }))).toBe(true);
    expect(isPaletteShortcut(key({ key: "Process", code: "KeyK", ctrlKey: true }))).toBe(true);
    // Dvorak types "t" on that key: Ctrl+T stays the browser's.
    expect(isPaletteShortcut(key({ key: "t", code: "KeyK", ctrlKey: true }))).toBe(false);
    expect(isPaletteShortcut(key({ key: "ㅏ", code: "KeyK" }))).toBe(false);
    expect(isPaletteShortcut(key({ key: "ㅏ", code: "KeyK", ctrlKey: true, altKey: true }))).toBe(
      false,
    );
  });

  it("opens with Ctrl+K on a Korean keyboard layout", async () => {
    const queryClient = makeQueryClient();
    queryClient.setQueryData(listProjectsQueryKey(), PROJECTS);
    renderStudio(<PaletteHarness />, { user: TEST_USER, queryClient });
    fireEvent.keyDown(document, { key: "ㅏ", code: "KeyK", ctrlKey: true });
    expect(await screen.findByRole("dialog")).toBeTruthy();
  });

  it("opens with Ctrl+K, focused on the search field", async () => {
    const queryClient = makeQueryClient();
    queryClient.setQueryData(listProjectsQueryKey(), PROJECTS);
    renderStudio(<PaletteHarness />, { user: TEST_USER, queryClient });
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("combobox")));
  });
});

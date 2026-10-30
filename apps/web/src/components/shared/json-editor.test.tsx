// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JsonDiff } from "./json-diff";
import { JsonEditor } from "./json-editor";
import type { JsonParseResult } from "./json-parse";
import { renderWithIntl } from "./test-utils";

afterEach(cleanup);

function Harness({
  initial,
  onResult,
}: {
  initial: string;
  onResult: (text: string, result: JsonParseResult) => void;
}) {
  const [text, setText] = useState(initial);
  return (
    <JsonEditor
      value={text}
      onChange={(next, result) => {
        setText(next);
        onResult(next, result);
      }}
    />
  );
}

describe("JsonEditor", () => {
  it("uses a labelled textarea where Monaco is not loaded and reports valid JSON", () => {
    renderWithIntl(<Harness initial='{"a": 1}' onResult={() => {}} />);
    const editor = screen.getByRole("textbox", { name: "JSON editor" });
    expect(editor.tagName).toBe("TEXTAREA");
    expect(editor.getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Valid JSON");
  });

  it("shows live parse errors with line and column", () => {
    const onResult = vi.fn();
    renderWithIntl(<Harness initial='{"a": 1}' onResult={onResult} />);
    const editor = screen.getByRole("textbox", { name: "JSON editor" });

    fireEvent.change(editor, { target: { value: '{\n  "a": 1,\n}' } });
    expect(editor.getAttribute("aria-invalid")).toBe("true");
    expect(editor.getAttribute("aria-describedby")).toBe(screen.getByRole("status").id);
    expect(screen.getByRole("status").textContent).toBe(
      "Line 3, column 1: Expected a property name in double quotes.",
    );
    expect(onResult).toHaveBeenLastCalledWith(
      '{\n  "a": 1,\n}',
      expect.objectContaining({
        ok: false,
        error: expect.objectContaining({ line: 3, column: 1 }),
      }),
    );
    expect((screen.getByRole("button", { name: "Format" }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(editor, { target: { value: '{"a": @}' } });
    expect(screen.getByRole("status").textContent).toBe(
      "Line 1, column 7: Unexpected character “@”.",
    );

    fireEvent.change(editor, { target: { value: '{"a": [1,2]}' } });
    expect(screen.getByRole("status").textContent).toBe("Valid JSON");
    expect(onResult).toHaveBeenLastCalledWith('{"a": [1,2]}', { ok: true, value: { a: [1, 2] } });
  });

  it("formats valid JSON", () => {
    const onResult = vi.fn();
    renderWithIntl(<Harness initial='{"a":[1,2],"b":{"c":true}}' onResult={onResult} />);
    fireEvent.click(screen.getByRole("button", { name: "Format" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe(
      '{\n  "a": [\n    1,\n    2\n  ],\n  "b": {\n    "c": true\n  }\n}',
    );
    expect(onResult).toHaveBeenCalledWith(expect.any(String), {
      ok: true,
      value: { a: [1, 2], b: { c: true } },
    });
  });

  it("explains errors in Korean", () => {
    renderWithIntl(<JsonEditor value="[1, 2" onChange={() => {}} />, { locale: "ko" });
    expect(screen.getByRole("status").textContent).toBe("1행 6열: JSON이 중간에 끝났습니다.");
  });
});

describe("JsonDiff", () => {
  it("diffs pretty-printed values, ignoring key order", () => {
    const { container } = renderWithIntl(
      <JsonDiff
        before={{ summary: "Old", papers: 2, extra: [1] }}
        after={{ papers: 2, summary: "New", extra: [1] }}
      />,
    );
    expect(container.querySelector("del")?.textContent).toBe('  "summary": "Old"');
    expect(container.querySelector("ins")?.textContent).toBe('  "summary": "New"');
    expect(screen.getByText("1 line added, 1 line removed")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Changes" })).toBeTruthy();
  });

  it("says when nothing changed", () => {
    renderWithIntl(<JsonDiff before={{ a: 1, b: 2 }} after={{ b: 2, a: 1 }} />);
    expect(screen.getByText("No changes.")).toBeTruthy();
    expect(screen.queryByRole("region")).toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import { type JsonErrorCode, parseJson, sortJsonKeys, toJsonText } from "./json-parse";

function errorOf(text: string) {
  const result = parseJson(text);
  if (result.ok) {
    throw new Error(`expected an error for ${JSON.stringify(text)}`);
  }
  return result.error;
}

describe("parseJson", () => {
  it("returns the value of valid JSON", () => {
    expect(parseJson('{"a": [1, 2.5e3, -0, "x\\n\\u00e9"], "b": null, "c": true}')).toEqual({
      ok: true,
      value: { a: [1, 2500, -0, "x\né"], b: null, c: true },
    });
    expect(parseJson("  42 ")).toEqual({ ok: true, value: 42 });
  });

  const cases: [string, string, JsonErrorCode, number, number][] = [
    ["empty", "   ", "empty", 1, 1],
    ["trailing comma in an object", '{\n  "a": 1,\n}', "expected_property", 3, 1],
    ["trailing comma in an array", "[1, 2,]", "expected_value", 1, 7],
    ["missing comma", '{\n  "a": 1\n  "b": 2\n}', "expected_comma_or_brace", 3, 3],
    ["missing bracket comma", "[1 2]", "expected_comma_or_bracket", 1, 4],
    ["missing colon", '{"a" 1}', "expected_colon", 1, 6],
    ["single quotes", "{'a': 1}", "expected_property", 1, 2],
    ["bare word", '{"a": yes}', "unexpected_character", 1, 7],
    ["unterminated string", '{"a": "abc\n}', "unterminated_string", 1, 7],
    ["bad escape", '"a\\x"', "invalid_escape", 1, 3],
    ["raw tab in a string", '"a\tb"', "control_character", 1, 3],
    ["leading zero", "[01]", "invalid_number", 1, 2],
    ["lone minus", "-", "invalid_number", 1, 1],
    ["unclosed object", '{"a": 1', "unexpected_end", 1, 8],
    ["text after the value", '{"a": 1} x', "trailing_characters", 1, 10],
    ["comment", '{"a": 1 // note\n}', "expected_comma_or_brace", 1, 9],
  ];

  it.each(cases)("reports %s with its position", (_name, text, code, line, column) => {
    expect(errorOf(text)).toMatchObject({ code, line, column });
  });

  it("names the offending character", () => {
    expect(errorOf('{"a": @}')).toMatchObject({ code: "unexpected_character", character: "@" });
  });
});

describe("JSON text helpers", () => {
  it("pretty-prints, optionally with sorted keys", () => {
    expect(toJsonText({ b: 1, a: [{ d: 1, c: 2 }] }, { sortKeys: true })).toBe(
      '{\n  "a": [\n    {\n      "c": 2,\n      "d": 1\n    }\n  ],\n  "b": 1\n}',
    );
    expect(toJsonText(undefined)).toBe("");
    expect(sortJsonKeys([3, { z: 1, y: 2 }])).toEqual([3, { y: 2, z: 1 }]);
  });
});

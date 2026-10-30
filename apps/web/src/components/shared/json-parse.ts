/**
 * JSON parsing with errors people can act on: a message code (translated under
 * `shared.json.errors.*`) and the line and column of the first problem. Browsers word and
 * position `JSON.parse` errors differently, so a small strict scanner (RFC 8259) locates them.
 */

export type JsonErrorCode =
  | "empty"
  | "unexpected_end"
  | "unexpected_character"
  | "unterminated_string"
  | "invalid_escape"
  | "control_character"
  | "invalid_number"
  | "expected_property"
  | "expected_colon"
  | "expected_comma_or_brace"
  | "expected_comma_or_bracket"
  | "expected_value"
  | "trailing_characters";

export type JsonParseError = {
  code: JsonErrorCode;
  /** 0-based offset into the text (UTF-16 units). */
  offset: number;
  /** 1-based line and column of the offset. */
  line: number;
  column: number;
  /** The character at the offset, when there is one. */
  character?: string;
};

export type JsonParseResult = { ok: true; value: unknown } | { ok: false; error: JsonParseError };

class ScanError {
  readonly code: JsonErrorCode;
  readonly offset: number;

  constructor(code: JsonErrorCode, offset: number) {
    this.code = code;
    this.offset = offset;
  }
}

function isDigit(character: string | undefined): boolean {
  return character !== undefined && character >= "0" && character <= "9";
}

/** The first syntax error in `text`, or null if it is valid JSON. */
function scan(text: string): ScanError | null {
  let i = 0;
  const end = text.length;
  const fail = (code: JsonErrorCode, offset = i): never => {
    throw new ScanError(code, offset);
  };
  const whitespace = () => {
    while (
      i < end &&
      (text[i] === " " || text[i] === "\t" || text[i] === "\n" || text[i] === "\r")
    ) {
      i += 1;
    }
  };
  const string = () => {
    const start = i;
    i += 1;
    while (i < end) {
      const code = text.charCodeAt(i);
      if (code === 0x22) {
        i += 1;
        return;
      }
      if (code === 0x5c) {
        const escaped = text[i + 1];
        if (escaped === undefined) {
          fail("unterminated_string", start);
        } else if ('"\\/bfnrt'.includes(escaped)) {
          i += 2;
        } else if (escaped === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) {
          i += 6;
        } else {
          fail("invalid_escape");
        }
        continue;
      }
      if (code === 0x0a || code === 0x0d) {
        fail("unterminated_string", start); // most likely a missing closing quote
      }
      if (code < 0x20) {
        fail("control_character");
      }
      i += 1;
    }
    fail("unterminated_string", start);
  };
  const number = () => {
    const start = i;
    if (text[i] === "-") {
      i += 1;
    }
    if (text[i] === "0") {
      i += 1;
    } else if (isDigit(text[i])) {
      while (isDigit(text[i])) {
        i += 1;
      }
    } else {
      fail("invalid_number", start);
    }
    if (text[i] === ".") {
      i += 1;
      if (!isDigit(text[i])) {
        fail("invalid_number", start);
      }
      while (isDigit(text[i])) {
        i += 1;
      }
    }
    if (text[i] === "e" || text[i] === "E") {
      i += 1;
      if (text[i] === "+" || text[i] === "-") {
        i += 1;
      }
      if (!isDigit(text[i])) {
        fail("invalid_number", start);
      }
      while (isDigit(text[i])) {
        i += 1;
      }
    }
    if (/[0-9A-Za-z_.]/.test(text[i] ?? "")) {
      fail("invalid_number", start); // 01, 1x, 1.2.3
    }
  };
  const value = (): void => {
    whitespace();
    if (i >= end) {
      fail("unexpected_end");
    }
    const character = text[i];
    if (character === "{") {
      object();
    } else if (character === "[") {
      array();
    } else if (character === '"') {
      string();
    } else if (character === "-" || isDigit(character)) {
      number();
    } else if (text.startsWith("true", i)) {
      i += 4;
    } else if (text.startsWith("false", i)) {
      i += 5;
    } else if (text.startsWith("null", i)) {
      i += 4;
    } else {
      fail(
        character === "}" || character === "]" || character === "," || character === ":"
          ? "expected_value"
          : "unexpected_character",
      );
    }
  };
  const object = () => {
    i += 1;
    whitespace();
    if (text[i] === "}") {
      i += 1;
      return;
    }
    for (;;) {
      whitespace();
      if (i >= end) {
        fail("unexpected_end");
      }
      if (text[i] !== '"') {
        fail("expected_property");
      }
      string();
      whitespace();
      if (i >= end) {
        fail("unexpected_end");
      }
      if (text[i] !== ":") {
        fail("expected_colon");
      }
      i += 1;
      value();
      whitespace();
      if (i >= end) {
        fail("unexpected_end");
      }
      if (text[i] === ",") {
        i += 1;
        continue;
      }
      if (text[i] === "}") {
        i += 1;
        return;
      }
      fail("expected_comma_or_brace");
    }
  };
  const array = () => {
    i += 1;
    whitespace();
    if (text[i] === "]") {
      i += 1;
      return;
    }
    for (;;) {
      value();
      whitespace();
      if (i >= end) {
        fail("unexpected_end");
      }
      if (text[i] === ",") {
        i += 1;
        continue;
      }
      if (text[i] === "]") {
        i += 1;
        return;
      }
      fail("expected_comma_or_bracket");
    }
  };

  try {
    value();
    whitespace();
    if (i < end) {
      fail("trailing_characters");
    }
    return null;
  } catch (error) {
    if (error instanceof ScanError) {
      return error;
    }
    throw error;
  }
}

function position(text: string, offset: number): { line: number; column: number } {
  let line = 1;
  let lineStart = 0;
  for (
    let index = text.indexOf("\n");
    index !== -1 && index < offset;
    index = text.indexOf("\n", index + 1)
  ) {
    line += 1;
    lineStart = index + 1;
  }
  return { line, column: offset - lineStart + 1 };
}

function errorAt(text: string, code: JsonErrorCode, offset: number): JsonParseError {
  const bounded = Math.max(0, Math.min(offset, text.length));
  const character = text[bounded];
  return { code, offset: bounded, ...position(text, bounded), ...(character ? { character } : {}) };
}

export function parseJson(text: string): JsonParseResult {
  if (text.trim().length === 0) {
    return { ok: false, error: errorAt(text, "empty", 0) };
  }
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    const found = scan(text);
    // The scanner and JSON.parse agree on valid JSON; this guards against a browser oddity.
    return {
      ok: false,
      error: found
        ? errorAt(text, found.code, found.offset)
        : errorAt(text, "unexpected_character", 0),
    };
  }
}

/** A JSON value with object keys sorted (arrays keep their order), for stable comparisons. */
export function sortJsonKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortJsonKeys);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, sortJsonKeys((value as Record<string, unknown>)[key])]),
    );
  }
  return value;
}

/** Pretty-printed JSON (two-space indent); `undefined` and functions become an empty text. */
export function toJsonText(
  value: unknown,
  { sortKeys = false }: { sortKeys?: boolean } = {},
): string {
  return JSON.stringify(sortKeys ? sortJsonKeys(value) : value, null, 2) ?? "";
}

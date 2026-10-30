import { describe, expect, it } from "vitest";
import {
  compareStages,
  STAGE_META,
  STAGES,
  stageIcon,
  stageMeta,
  UNKNOWN_STAGE_ICON,
} from "@/lib/stage-meta";
import { buildFileTree, flattenFiles, normalizePath } from "./file-tree";
import { highlightLanguage } from "./shiki";
import { isSameOriginPath, paperFileUrl } from "./urls";

describe("buildFileTree", () => {
  it("nests folders, lists folders first and sorts naturally", () => {
    const tree = buildFileTree([
      "model.py",
      "configs/train.yaml",
      "tests/test_model.py",
      "configs/eval10.yaml",
      "configs/eval2.yaml",
      "README.md",
    ]);
    expect(tree.map((node) => `${node.kind}:${node.name}`)).toEqual([
      "folder:configs",
      "folder:tests",
      "file:model.py",
      "file:README.md",
    ]);
    expect(flattenFiles(tree)).toEqual([
      "configs/eval2.yaml",
      "configs/eval10.yaml",
      "configs/train.yaml",
      "tests/test_model.py",
      "model.py",
      "README.md",
    ]);
  });

  it("normalises paths and drops duplicates and empty ones", () => {
    expect(normalizePath("./src\\model.py")).toBe("src/model.py");
    const tree = buildFileTree(["src/a.py", "./src/a.py", "", "/"]);
    expect(flattenFiles(tree)).toEqual(["src/a.py"]);
  });
});

describe("stage metadata", () => {
  it("has the pipeline order, icons and colour tokens", () => {
    expect(STAGES).toEqual(["literature", "method", "coding", "experiment", "writing"]);
    expect(STAGE_META.coding).toMatchObject({
      order: 2,
      color: "var(--stage-coding)",
      colorFg: "var(--stage-coding-fg)",
      tokens: { color: "--stage-coding", colorFg: "--stage-coding-fg" },
    });
    expect(stageMeta("review")).toBeUndefined();
    expect(stageIcon("review")).toBe(UNKNOWN_STAGE_ICON);
    expect(["writing", "review", "literature", "coding"].sort(compareStages)).toEqual([
      "literature",
      "coding",
      "writing",
      "review",
    ]);
  });
});

describe("helpers", () => {
  it("maps languages and extensions to highlighter grammars", () => {
    expect(highlightLanguage("Python")).toBe("python");
    expect(highlightLanguage("", "configs/train.yml")).toBe("yaml");
    expect(highlightLanguage("shell")).toBe("bash");
    expect(highlightLanguage("text", "notes.txt")).toBeNull();
  });

  it("only accepts same-origin download paths", () => {
    expect(isSameOriginPath(paperFileUrl("arxiv:1904.96234"))).toBe(true);
    expect(paperFileUrl("arxiv:1904.96234")).toBe("/api/v1/papers/arxiv%3A1904.96234/file");
    for (const href of [
      "https://evil.example/x",
      "//evil.example/x",
      "/\\evil.example",
      "javascript:alert(1)",
      "/a\nb",
    ]) {
      expect(isSameOriginPath(href), href).toBe(false);
    }
  });
});

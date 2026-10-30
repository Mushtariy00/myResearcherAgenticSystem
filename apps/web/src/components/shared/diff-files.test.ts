import { describe, expect, it } from "vitest";
import type { CodeFile } from "@/client";
import { countLines, diffCodeFiles, lineChanges, sortByStatus } from "./diff-files";
import { unifiedDiffRows } from "./unified-diff";

function file(path: string, content: string, role: CodeFile["role"] = "model"): CodeFile {
  return { path, content, role, language: "python" };
}

const before = [
  file("model.py", "import torch\n\nclass DepthNet:\n    pass\n"),
  file("losses.py", "def silog(pred, target):\n    return 0\n", "loss"),
  file("configs/train.yaml", "epochs: 10\nlr: 0.001\n", "config"),
  file("README.md", "# Model\n", "docs"),
  file("notes/old_name.py", "VALUE = 1\n", "docs"),
];

const after = [
  // Changed: one line replaced, one added.
  file(
    "model.py",
    "import torch\n\nclass DepthNet(torch.nn.Module):\n    pass\n\nNAME = 'depth'\n",
  ),
  // Unchanged apart from Windows line endings.
  file("losses.py", "def silog(pred, target):\r\n    return 0\r\n", "loss"),
  file("configs/train.yaml", "epochs: 10\nlr: 0.001\n", "config"),
  // New file.
  file("tests/test_model.py", "def test_shape():\n    assert True\n", "test"),
  // Moved without edits.
  file("notes/new_name.py", "VALUE = 1\n", "docs"),
];

describe("diffCodeFiles", () => {
  const changes = diffCodeFiles(before, after);
  const byPath = new Map(changes.map((change) => [change.path, change]));

  it("classifies every file as added, removed, modified, renamed or unchanged", () => {
    expect(Object.fromEntries(changes.map((change) => [change.path, change.status]))).toEqual({
      "configs/train.yaml": "unchanged",
      "losses.py": "unchanged",
      "model.py": "modified",
      "notes/new_name.py": "renamed",
      "README.md": "removed",
      "tests/test_model.py": "added",
    });
    expect(byPath.get("notes/new_name.py")?.previousPath).toBe("notes/old_name.py");
  });

  it("counts added and removed lines", () => {
    expect(byPath.get("model.py")).toMatchObject({ additions: 3, deletions: 1 });
    expect(byPath.get("tests/test_model.py")).toMatchObject({ additions: 2, deletions: 0 });
    expect(byPath.get("README.md")).toMatchObject({ additions: 0, deletions: 1 });
    expect(byPath.get("losses.py")).toMatchObject({ additions: 0, deletions: 0 });
  });

  it("keeps both versions for the viewer and sorts paths naturally", () => {
    const modified = byPath.get("model.py");
    expect(modified?.before?.content).toContain("class DepthNet:");
    expect(modified?.after?.content).toContain("torch.nn.Module");
    expect(
      diffCodeFiles([], [file("b10.py", ""), file("b2.py", ""), file("a.py", "")]).map(
        (c) => c.path,
      ),
    ).toEqual(["a.py", "b2.py", "b10.py"]);
  });

  it("normalises paths and treats identical inputs as unchanged", () => {
    const changes = diffCodeFiles([file("./src\\model.py", "x\n")], [file("src/model.py", "x\n")]);
    expect(changes).toEqual([
      expect.objectContaining({ path: "src/model.py", status: "unchanged" }),
    ]);
    expect(diffCodeFiles([], [])).toEqual([]);
  });

  it("lists changed files before unchanged ones", () => {
    expect(sortByStatus(changes).map((change) => change.status)).toEqual([
      "modified",
      "added",
      "renamed",
      "removed",
      "unchanged",
      "unchanged",
    ]);
  });
});

describe("line counting", () => {
  it("ignores a missing final newline and CRLF endings", () => {
    expect(countLines("")).toBe(0);
    expect(countLines("a\nb\n")).toBe(2);
    expect(countLines("a\r\nb")).toBe(2);
    expect(lineChanges("a\nb", "a\nb\n")).toEqual({ additions: 0, deletions: 0 });
    expect(lineChanges("a\nb\n", "a\nc\n")).toEqual({ additions: 1, deletions: 1 });
  });
});

describe("unifiedDiffRows", () => {
  const old = Array.from({ length: 20 }, (_, index) => `line ${index + 1}`).join("\n");
  const next = old.replace("line 10", "line ten").replace("line 20", "line 20\nline 21");

  it("numbers old and new lines and reports the unchanged lines it skips", () => {
    const rows = unifiedDiffRows(old, next, 2);
    const hunks = rows.filter((row) => row.kind === "hunk");
    // Lines 1-7 come before the first hunk (8-12), lines 13-17 between the hunks.
    expect(hunks.map((hunk) => ("skipped" in hunk ? hunk.skipped : null))).toEqual([7, 5]);
    expect(rows).toContainEqual({ kind: "removed", text: "line 10", oldLine: 10 });
    expect(rows).toContainEqual({ kind: "added", text: "line ten", newLine: 10 });
    expect(rows).toContainEqual({ kind: "context", text: "line 9", oldLine: 9, newLine: 9 });
    expect(rows).toContainEqual({ kind: "added", text: "line 21", newLine: 21 });
  });

  it("shows a new file as all additions and identical texts as nothing", () => {
    const rows = unifiedDiffRows("", "a\nb\n");
    expect(rows.filter((row) => row.kind === "added")).toHaveLength(2);
    expect(unifiedDiffRows("same\n", "same\n")).toEqual([]);
  });
});

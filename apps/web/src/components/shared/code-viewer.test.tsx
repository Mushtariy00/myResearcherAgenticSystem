// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CodeFile } from "@/client";
import { CodeDiff } from "./code-diff";
import { CodeViewer } from "./code-viewer";
import { renderWithIntl } from "./test-utils";

afterEach(cleanup);

const files: CodeFile[] = [
  {
    path: "model.py",
    language: "python",
    role: "model",
    content: "import torch\n\n\nclass DepthNet(torch.nn.Module):\n    pass\n",
  },
  {
    path: "configs/train.yaml",
    language: "yaml",
    role: "config",
    content: "epochs: 24\nlr: 0.0003",
  },
  { path: "README.md", language: "markdown", role: "docs", content: "# DepthNet\n" },
];

describe("CodeViewer", () => {
  it("shows a file tree and the selected file with line numbers, role and highlighting", async () => {
    const onSelectPath = vi.fn();
    const { container } = renderWithIntl(
      <CodeViewer
        files={files}
        defaultPath="model.py"
        onSelectPath={onSelectPath}
        downloadUrl="/api/v1/artifacts/a1"
      />,
    );
    const tree = screen.getByRole("navigation", { name: "Files" });
    expect(
      within(tree).getByRole("button", { name: "configs" }).getAttribute("aria-expanded"),
    ).toBe("true");
    const code = screen.getByRole("region", { name: "Contents of model.py" });
    expect(code.textContent).toContain("class DepthNet(torch.nn.Module):");
    expect(screen.getByText("5 lines")).toBeTruthy();
    expect(screen.getByText("Model")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy model.py" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download all files/ }).getAttribute("href")).toBe(
      "/api/v1/artifacts/a1",
    );
    // The shared Shiki highlighter colours tokens with both themes as CSS variables.
    await waitFor(
      () =>
        expect(container.querySelector('[data-code] > span[style*="--shiki-dark"]')).not.toBeNull(),
      { timeout: 10_000 },
    );

    fireEvent.click(within(tree).getByRole("button", { name: "train.yaml" }));
    expect(onSelectPath).toHaveBeenCalledWith("configs/train.yaml");
    expect(
      screen.getByRole("region", { name: "Contents of configs/train.yaml" }).textContent,
    ).toContain("lr: 0.0003");
    expect(
      within(tree).getByRole("button", { name: "train.yaml" }).getAttribute("aria-current"),
    ).toBe("true");

    fireEvent.click(within(tree).getByRole("button", { name: "configs" }));
    expect(within(tree).queryByRole("button", { name: "train.yaml" })).toBeNull();
  });

  it("says when there are no files", () => {
    renderWithIntl(<CodeViewer files={[]} />);
    expect(screen.getByText("No files.")).toBeTruthy();
  });
});

describe("CodeDiff", () => {
  const next: CodeFile[] = [
    {
      ...files[0],
      content: "import torch\n\n\nclass DepthNet(torch.nn.Module):\n    depth = 4\n",
    } as CodeFile,
    files[1] as CodeFile,
    {
      path: "tests/test_model.py",
      language: "python",
      role: "test",
      content: "def test():\n    pass\n",
    },
  ];

  it("lists changed files with markers and shows a unified diff without Monaco", () => {
    const { container } = renderWithIntl(<CodeDiff before={files} after={next} />);
    const list = screen.getByRole("navigation", { name: "Files" });
    expect(within(list).getByText("3 files changed")).toBeTruthy();
    expect(
      within(list).getByRole("button", {
        name: /model\.py.*Changed, 1 line added, 1 line removed/,
      }),
    ).toBeTruthy();
    expect(within(list).getByRole("button", { name: /test_model\.py.*Added/ })).toBeTruthy();
    expect(within(list).getByRole("button", { name: /README\.md.*Deleted/ })).toBeTruthy();
    // Unchanged files are hidden until asked for.
    expect(within(list).queryByRole("button", { name: /train\.yaml/ })).toBeNull();

    // The first changed file is open in the lightweight diff (Monaco needs a wide container).
    const diff = screen.getByRole("region", { name: "Changes in model.py" });
    expect(diff.querySelector("del")?.textContent).toBe("    pass");
    expect(diff.querySelector("ins")?.textContent).toBe("    depth = 4");
    expect(container.querySelector('[data-slot="monaco-diff"]')).toBeNull();

    fireEvent.click(within(list).getByRole("button", { name: /README\.md/ }));
    expect(
      screen.getByRole("region", { name: "Changes in README.md" }).querySelector("del")
        ?.textContent,
    ).toBe("# DepthNet");

    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(within(list).getByRole("button", { name: /train\.yaml.*Unchanged/ }));
    expect(screen.getByText("No changes in this file.")).toBeTruthy();
  });

  it("says when the versions are identical", () => {
    renderWithIntl(<CodeDiff before={files} after={files} />);
    expect(screen.getByText("0 files changed")).toBeTruthy();
    expect(screen.getByText("The two versions are identical.")).toBeTruthy();
  });
});

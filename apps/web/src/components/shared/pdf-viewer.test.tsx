// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { PdfViewerImpl } from "./pdf-viewer-impl";
import { renderWithIntl } from "./test-utils";

/**
 * PDF.js cannot run in jsdom, so react-pdf is replaced by a stand-in that behaves like it:
 * the document reports its page count, the page reports its text items, renders the text layer
 * through `customTextRenderer` and then reports that the text layer is ready.
 */
const pdf = vi.hoisted(() => ({
  fail: false,
  pages: {
    1: ["Abstract. Depth from one image."],
    2: ["The EfficientNet-B3 encoder is", "initialized from ImageNet weights."],
    3: ["Results on NYU Depth v2."],
  } as Record<number, string[]>,
}));

vi.mock("react-pdf", async () => {
  const React = await import("react");
  type DocumentProps = {
    children?: React.ReactNode;
    onLoadSuccess?: (document: { numPages: number }) => void;
    onLoadError?: (error: Error) => void;
  };
  function Document({ children, onLoadSuccess, onLoadError }: DocumentProps) {
    const [loaded, setLoaded] = React.useState(false);
    React.useEffect(() => {
      if (pdf.fail) {
        onLoadError?.(new Error("404"));
        return;
      }
      onLoadSuccess?.({ numPages: 3 });
      setLoaded(true);
    }, [onLoadError, onLoadSuccess]);
    return <div data-testid="document">{loaded ? children : null}</div>;
  }
  type PageProps = {
    pageNumber: number;
    width?: number;
    scale?: number;
    inputRef?: React.Ref<HTMLDivElement>;
    customTextRenderer?: (item: { str: string; itemIndex: number }) => string;
    onLoadSuccess?: (page: { originalWidth: number }) => void;
    onGetTextSuccess?: (content: { items: { str: string }[] }) => void;
    onRenderTextLayerSuccess?: () => void;
  };
  function Page(props: PageProps) {
    const items = pdf.pages[props.pageNumber] ?? [];
    const latest = React.useRef(props);
    latest.current = props;
    React.useEffect(() => {
      latest.current.onLoadSuccess?.({ originalWidth: 600 });
      latest.current.onGetTextSuccess?.({ items: items.map((str) => ({ str })) });
    }, [items]);
    const html = items.map(
      (str, itemIndex) => props.customTextRenderer?.({ str, itemIndex }) ?? str,
    );
    const key = html.join("|");
    React.useEffect(() => {
      latest.current.onRenderTextLayerSuccess?.();
    }, [key]);
    return (
      <div
        ref={props.inputRef}
        data-testid="page"
        data-page={props.pageNumber}
        data-scale={props.scale}
      >
        {html.map((item, index) => (
          // biome-ignore lint/security/noDangerouslySetInnerHtml: stands in for the PDF.js text layer
          // biome-ignore lint/suspicious/noArrayIndexKey: text items are positional
          <span key={index} dangerouslySetInnerHTML={{ __html: item }} />
        ))}
      </div>
    );
  }
  return { Document, Page, pdfjs: { GlobalWorkerOptions: { workerPort: null } } };
});

const scrollIntoView = vi.fn();

beforeAll(() => {
  Element.prototype.scrollIntoView = scrollIntoView;
});

afterEach(() => {
  cleanup();
  pdf.fail = false;
  scrollIntoView.mockClear();
});

const quotes = [
  { quote: "The EfficientNet-B3 encoder is initialized from ImageNet", page: 2 },
  { quote: "A sentence that is not in the paper", page: 3 },
];

const page = () => screen.getByTestId("page");

describe("PdfViewer", () => {
  it("opens at the first quote, highlights it across text items and scrolls to it", async () => {
    renderWithIntl(<PdfViewerImpl url="/api/v1/papers/p/file" title="GeoDiff" quotes={quotes} />);
    await waitFor(() => expect(page().getAttribute("data-page")).toBe("2"));
    await waitFor(() => expect(page().querySelectorAll("mark.pdf-quote")).toHaveLength(2));
    const marks = [...page().querySelectorAll("mark")];
    expect(marks.map((mark) => mark.textContent)).toEqual([
      "The EfficientNet-B3 encoder is",
      "initialized from ImageNet",
    ]);
    expect(marks.every((mark) => mark.hasAttribute("data-active"))).toBe(true);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    expect(screen.getByText("Quote 1 of 2, page 2")).toBeTruthy();
    expect(screen.getByRole("region", { name: "PDF: GeoDiff" })).toBeTruthy();
    expect(screen.getByRole("toolbar", { name: "PDF controls" })).toBeTruthy();
  });

  it("moves between quotes and says when one cannot be found", async () => {
    const onActiveQuoteChange = vi.fn();
    renderWithIntl(
      <PdfViewerImpl
        url="/api/v1/papers/p/file"
        quotes={quotes}
        onActiveQuoteChange={onActiveQuoteChange}
      />,
    );
    await waitFor(() => expect(page().getAttribute("data-page")).toBe("2"));
    fireEvent.click(screen.getByRole("button", { name: "Next quote" }));
    expect(onActiveQuoteChange).toHaveBeenCalledWith(1);
    await waitFor(() => expect(page().getAttribute("data-page")).toBe("3"));
    await waitFor(() =>
      expect(screen.getAllByText("Quote 2 could not be found on page 3.").length).toBeGreaterThan(
        0,
      ),
    );
    expect(screen.getByText("Quote 2 of 2")).toBeTruthy();
  });

  it("turns pages and zooms from the keyboard and the toolbar", async () => {
    renderWithIntl(<PdfViewerImpl url="/api/v1/papers/p/file" initialPage={1} />);
    await waitFor(() => expect(page().getAttribute("data-page")).toBe("1"));
    const region = screen.getByRole("region", { name: "PDF document" });

    fireEvent.keyDown(region, { key: "PageDown" });
    expect(page().getAttribute("data-page")).toBe("2");
    expect(screen.getByText("Page 2 of 3")).toBeTruthy();
    fireEvent.keyDown(region, { key: "PageDown" });
    fireEvent.keyDown(region, { key: "PageDown" });
    expect(page().getAttribute("data-page")).toBe("3"); // stops at the last page
    fireEvent.keyDown(region, { key: "PageUp" });
    expect(page().getAttribute("data-page")).toBe("2");

    // Fit width is on; zooming switches to a fixed scale, and the fit button restores it.
    const fit = screen.getByRole("button", { name: "Fit to width" });
    expect(fit.getAttribute("aria-pressed")).toBe("true");
    fireEvent.keyDown(region, { key: "+" });
    expect(page().getAttribute("data-scale")).toBe("1.1");
    expect(fit.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(page().getAttribute("data-scale")).toBe("1");
    fireEvent.keyDown(region, { key: "-" });
    expect(page().getAttribute("data-scale")).toBe("0.9");
    fireEvent.click(fit);
    expect(fit.getAttribute("aria-pressed")).toBe("true");

    const input = screen.getByRole("textbox", { name: "Page number" });
    fireEvent.change(input, { target: { value: "1" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(page().getAttribute("data-page")).toBe("1");
    // Disabled toolbar buttons stay focusable (toolbar pattern), so they use aria-disabled.
    expect(
      screen.getByRole("button", { name: "Previous page" }).getAttribute("aria-disabled"),
    ).toBe("true");
  });

  it("shows an error with a retry", async () => {
    pdf.fail = true;
    renderWithIntl(<PdfViewerImpl url="/api/v1/papers/missing/file" />);
    await waitFor(() => expect(screen.getByText("Could not load the PDF.")).toBeTruthy());
    pdf.fail = false;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    });
    await waitFor(() => expect(page().getAttribute("data-page")).toBe("1"));
  });
});

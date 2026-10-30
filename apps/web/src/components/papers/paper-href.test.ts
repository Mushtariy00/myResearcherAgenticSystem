import { describe, expect, it } from "vitest";
import { paperFileUrl } from "@/components/shared/urls";
import { paperHref, paperIdFromSegments } from "./paper-href";

const IDS = [
  "doi:10.5555/depth.2024",
  "arxiv:2401.12345",
  "arxiv:hep-th/9901001v2",
  "openalex:W123/with spaces?and#marks",
];

/**
 * What Next.js hands `/papers/[...paperId]` for a request path: the path after /papers/ split
 * at every "/", each part decoded by the route matcher and encoded again for the page.
 */
function segmentsFor(href: string): string[] {
  return href
    .slice("/papers/".length)
    .split("/")
    .map((part) => encodeURIComponent(decodeURIComponent(part)));
}

describe("paper links", () => {
  it("encode the whole id as one segment, as the PDF route of the API does", () => {
    expect(paperHref("doi:10.5555/depth.2024")).toBe("/papers/doi%3A10.5555%2Fdepth.2024");
    for (const id of IDS) {
      expect(paperFileUrl(id)).toBe(`/api/v1${paperHref(id)}/file`);
    }
  });

  it("come back as the same id on the paper page", () => {
    for (const id of IDS) {
      expect(paperIdFromSegments(segmentsFor(paperHref(id)))).toBe(id);
    }
  });

  it("still find the paper when a proxy decoded the slashes", () => {
    expect(paperIdFromSegments(["doi%3A10.5555", "depth.2024"])).toBe("doi:10.5555/depth.2024");
    expect(paperIdFromSegments("arxiv%3A2401.12345")).toBe("arxiv:2401.12345");
  });

  it("reject ids that are empty or not valid percent-encoding", () => {
    expect(paperIdFromSegments([])).toBeNull();
    expect(paperIdFromSegments(undefined)).toBeNull();
    expect(paperIdFromSegments(["%E0%A4%A"])).toBeNull();
    expect(paperIdFromSegments(["%20"])).toBeNull();
  });
});

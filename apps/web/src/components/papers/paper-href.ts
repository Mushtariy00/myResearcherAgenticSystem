/**
 * Links to a paper's page in the library. Paper ids contain colons and slashes
 * (`doi:10.5555/depth.2024`), so the id is encoded as a single path segment, exactly as
 * `paperFileUrl` encodes it for the API: `/papers/doi%3A10.5555%2Fdepth.2024`.
 *
 * The page is a catch-all route (`/papers/[...paperId]`): when something on the way decodes
 * `%2F` into `/`, the id arrives as several segments and is joined back together.
 */

export const PAPER_LIBRARY_PATH = "/papers";

/** The Classic page of a paper. */
export function paperHref(paperId: string): string {
  return `${PAPER_LIBRARY_PATH}/${encodeURIComponent(paperId)}`;
}

/**
 * The paper id from the segments of `/papers/[...paperId]`. Next.js hands the page every
 * segment percent-encoded, as it appears in the URL: each one is decoded once, then the
 * segments are joined with "/". Null for an empty id or broken percent-encoding (a lone "%").
 */
export function paperIdFromSegments(
  segments: readonly string[] | string | undefined,
): string | null {
  const parts = typeof segments === "string" ? [segments] : (segments ?? []);
  try {
    const id = parts.map((segment) => decodeURIComponent(segment)).join("/");
    return id.trim() === "" ? null : id;
  } catch {
    return null;
  }
}

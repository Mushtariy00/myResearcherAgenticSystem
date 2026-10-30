/**
 * Same-origin URLs of files the API streams as attachments (`nosniff`, `Content-Disposition:
 * attachment`). Caddy routes /api/v1/* to the API, so relative paths work in both interfaces.
 */

export function artifactUrl(artifactId: string): string {
  return `/api/v1/artifacts/${encodeURIComponent(artifactId)}`;
}

export function paperFileUrl(paperId: string): string {
  return `/api/v1/papers/${encodeURIComponent(paperId)}/file`;
}

/**
 * True for a path on this site ("/api/v1/..."), false for absolute or protocol-relative URLs
 * (and backslash tricks browsers treat as such): downloads never leave the origin.
 */
export function isSameOriginPath(href: string): boolean {
  return /^\/(?![/\\])/.test(href) && !/\p{Cc}/u.test(href);
}

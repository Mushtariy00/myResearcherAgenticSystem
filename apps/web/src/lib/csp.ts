/**
 * The Content-Security-Policy of every page (docs/PLAN.md, browser hardening).
 *
 * Scripts run only with the request's nonce, or when a script that had it loads them
 * ('strict-dynamic'). Next.js puts the nonce on its own scripts during rendering; the two inline
 * snippets of our own (next-themes' theme script and InlineScript) get it from the root layout.
 * Styles allow inline attributes: React style props, Shiki and motion set them, and a nonce
 * can't cover attributes. Development adds what React's debugging and hot reload need.
 */
export function contentSecurityPolicy(nonce: string, development: boolean): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self' data:",
    `connect-src 'self'${development ? " ws:" : ""}`,
    // pdf.js and Monaco workers come from this site; canvas-confetti may start one from a blob.
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** A fresh, unguessable nonce for one response. */
export function newNonce(): string {
  return btoa(crypto.randomUUID());
}

"use client";

import { useNonce } from "@/components/nonce";

/**
 * A script that runs while the browser parses the server HTML, before the first paint (see
 * Next's "preventing flash before hydration" guide). Only that server-rendered copy ever runs:
 * React never executes scripts it inserts itself.
 *
 * It is a client component so that the client really renders its own copy, an inert data block
 * (`text/plain`): React warns about every executable `<script>` it creates on the client, and a
 * server component would hand a client navigation (Classic → Studio) the server's
 * `text/javascript` script through the RSC payload. While hydrating, `suppressHydrationWarning`
 * accepts the different type. Only for small static snippets written in this codebase. The
 * server copy carries the page's CSP nonce, without which the browser would not run it.
 */
export function InlineScript({ html }: { html: string }) {
  const nonce = useNonce();
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      nonce={nonce}
      suppressHydrationWarning
      // biome-ignore lint/security/noDangerouslySetInnerHtml: static snippets from this codebase only
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

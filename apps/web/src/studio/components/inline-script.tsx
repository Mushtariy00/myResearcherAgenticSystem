/**
 * A script that runs while the browser parses the server HTML, before the first paint (see
 * Next's "preventing flash before hydration" guide). Scripts inserted on the client never run,
 * so on the client it renders as inert `text/plain`; `suppressHydrationWarning` accepts the
 * difference. Only for small static snippets written in this codebase.
 */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      // biome-ignore lint/security/noDangerouslySetInnerHtml: static snippets from this codebase only
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

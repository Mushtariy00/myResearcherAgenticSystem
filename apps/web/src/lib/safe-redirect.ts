const BASE = "http://app.invalid";

/**
 * Where to go after signing in. Only same-site paths are allowed, so a crafted
 * `/login?next=https://evil.example` cannot bounce the user to another site.
 */
export function safeNextPath(value: string | null | undefined, fallback = "/"): string {
  if (!value?.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return fallback;
  }
  // Control characters and whitespace have no place in our paths.
  for (const char of value) {
    const code = char.charCodeAt(0);
    if (code <= 0x20 || code === 0x7f) {
      return fallback;
    }
  }
  let url: URL;
  try {
    url = new URL(value, BASE);
  } catch {
    return fallback;
  }
  if (url.origin !== BASE || url.pathname.startsWith("/api/") || url.pathname === "/login") {
    return fallback;
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

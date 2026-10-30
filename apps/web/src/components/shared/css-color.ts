/**
 * Turns CSS colour expressions into colours a canvas renderer can use. Charts and editors draw
 * on canvas or take theme objects, so they cannot follow CSS variables by themselves: they ask
 * here what a variable means at a given element (Classic, dark, or the Studio scope).
 */

let context: CanvasRenderingContext2D | null | undefined;

function canvasContext(): CanvasRenderingContext2D | null {
  if (context === undefined) {
    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    context = canvas.getContext("2d", { willReadFrequently: true });
  }
  return context;
}

/** `rgb()`/`rgba()` for any CSS colour (oklch, color-mix, color()...), via one canvas pixel. */
export function toRgb(color: string): string {
  const value = color.trim();
  if (value === "" || /^(rgba?\(|#[0-9a-f]{3,8}$)/i.test(value)) {
    return value;
  }
  const ctx = canvasContext();
  if (!ctx) {
    return value;
  }
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = "#000";
  ctx.fillStyle = value;
  ctx.fillRect(0, 0, 1, 1);
  const [r = 0, g = 0, b = 0, a = 255] = ctx.getImageData(0, 0, 1, 1).data;
  return a >= 255
    ? `rgb(${r}, ${g}, ${b})`
    : `rgba(${r}, ${g}, ${b}, ${Math.round((a / 255) * 1000) / 1000})`;
}

/** `#rrggbb` (alpha dropped) for APIs that only accept hex, such as Monaco themes. */
export function toHex(color: string): string {
  const rgb = toRgb(color);
  const match = /^rgba?\((\d+),\s*(\d+),\s*(\d+)/i.exec(rgb);
  if (!match) {
    return /^#[0-9a-f]{6}$/i.test(rgb) ? rgb : "#000000";
  }
  return `#${match
    .slice(1, 4)
    .map((part) => Number(part).toString(16).padStart(2, "0"))
    .join("")}`;
}

/**
 * Resolves each expression (for example `var(--chart-grid, var(--border))`) as it applies inside
 * `scope`, and returns canvas-ready colours under the same keys.
 */
export function resolveColors<K extends string>(
  scope: Element,
  expressions: Readonly<Record<K, string>>,
): Record<K, string> {
  const probe = document.createElement("span");
  probe.style.display = "none";
  scope.appendChild(probe);
  const resolved = {} as Record<K, string>;
  try {
    for (const key of Object.keys(expressions) as K[]) {
      probe.style.color = "";
      probe.style.color = expressions[key];
      resolved[key] = toRgb(getComputedStyle(probe).color);
    }
  } finally {
    probe.remove();
  }
  return resolved;
}

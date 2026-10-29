/** Money arrives from the API as decimal strings ("12.50"); null and junk count as zero. */
export function toAmount(value: string | number | null | undefined): number {
  if (value === null || value === undefined) {
    return 0;
  }
  const amount = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(amount) ? amount : 0;
}

/** Share of a budget used, clamped to 0..100 (no budget means nothing can be used). */
export function percentUsed(spent: number, budget: number): number {
  if (budget <= 0) {
    return spent > 0 ? 100 : 0;
  }
  return Math.min(100, Math.max(0, (spent / budget) * 100));
}

/** "$1.50" in every UI language (Korean would otherwise print "US$1.50"). */
export const USD = { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol" } as const;

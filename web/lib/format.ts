export const CATEGORY_LABEL: Record<string, string> = {
  results: "Results",
  "M&A": "M&A",
  fund_raise: "Fund raise",
  management_change: "Management",
  litigation: "Litigation",
  insider_trading: "Insider trade",
  earnings_call: "Earnings call",
  investor_meetings: "Investor meet",
  credit_rating: "Credit rating",
  dividend: "Dividend",
  bonus_split: "Bonus / split",
  capex: "Capex",
  press_release: "Press release",
  postal_ballot: "Postal ballot",
  agm_egm: "AGM / EGM",
  pledging: "Pledging",
  unclassified: "Paperwork",
};

export function cr(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  const abs = Math.abs(v);
  const s = abs >= 100 ? Math.round(abs).toLocaleString("en-IN") : abs.toLocaleString("en-IN", { maximumFractionDigits: 1 });
  return (v < 0 ? "−" : "") + "₹" + s;
}

export function pct(v: number | null | undefined, digits = 1, sign = true): string {
  if (v === null || v === undefined) return "–";
  const s = Math.abs(v).toFixed(digits);
  if (!sign) return `${v < 0 ? "−" : ""}${s}%`;
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${s}%`;
}

export function pp(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}pp`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return "–";
  return v.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function tone(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "text-ink-2";
  return v > 0 ? "text-up" : "text-down";
}

const DAY = 86400000;

export function when(iso: string | null, asOf: string): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const now = new Date(asOf).getTime();
  const diff = now - t;
  const d = new Date(iso);
  const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
  if (diff < 0) return time;
  if (diff < 3600000) return `${Math.max(1, Math.round(diff / 60000))}m ago`;
  if (diff < DAY && d.getDate() === new Date(asOf).getDate()) return `${Math.round(diff / 3600000)}h ago`;
  if (diff < 6 * DAY) return `${d.toLocaleDateString("en-IN", { weekday: "short", timeZone: "Asia/Kolkata" })} ${time}`;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
}

export function asOfLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
}

export function istDate(iso: string): string {
  // YYYY-MM-DD in IST
  const d = new Date(new Date(iso).getTime() + 5.5 * 3600000);
  return d.toISOString().slice(0, 10);
}

export const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  kept: { label: "Kept", cls: "text-up bg-up-soft" },
  missed: { label: "Missed", cls: "text-down bg-down-soft" },
  revised: { label: "Revised", cls: "text-accent bg-accent-soft" },
  dropped: { label: "Dropped", cls: "text-accent bg-accent-soft" },
  pending: { label: "Pending", cls: "text-ink-2 bg-surface-2" },
  unverifiable: { label: "Can't check", cls: "text-ink-3 bg-surface-2" },
};

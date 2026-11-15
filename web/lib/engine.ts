// The filter. Facts come precomputed from the pipeline; this file applies MY
// preferences (window, thresholds, watched categories, pillars) on the device.

import type { Category, Config, Filing, Holding, Pillar, PriceStock, Session } from "./types";
import { CATEGORY_LABEL, istDate } from "./format";

export type WindowKey = "24h" | "3d" | "7d" | "14d" | "custom";
export interface Win { key: WindowKey; from?: string; to?: string }

export interface Settings {
  volume_multiple: number;
  move_pct: number;
  overrides: Record<string, { volume_multiple?: number; move_pct?: number }>;
  watched: Category[];
  pillars: Record<string, Pillar[]>;
  theme: "system" | "dark" | "light";
  onboarded: boolean;
}

export function defaultSettings(c: Config): Settings {
  return {
    volume_multiple: c.alerts.volume_multiple,
    move_pct: c.alerts.move_pct,
    overrides: c.alerts.overrides || {},
    watched: c.watched_categories,
    pillars: c.pillars || {},
    theme: "system",
    onboarded: false,
  };
}

export type ReasonKind = "pillar-broken" | "pillar-risk" | "pillar-holds" | "promise" | "orphan" | "unexplained" | "watched" | "transcript";
export interface Reason { kind: ReasonKind; text: string }

export interface Move {
  symbol: string; date: string; change_pct: number | null; vol_multiple: number | null;
  why: ("volume" | "move")[]; explainedBy: Filing | null; series: Session[];
}

export interface FilingEntry { kind: "filing"; filing: Filing; tier: 1 | 2 | 3; reasons: Reason[]; reaction: Move | null }
export interface MoveEntry { kind: "move"; move: Move; tier: 1; reasons: Reason[] }
export type Entry = FilingEntry | MoveEntry;

const RANK: Record<ReasonKind, number> = {
  "pillar-broken": 0, orphan: 1, promise: 2, unexplained: 3, "pillar-risk": 4, "pillar-holds": 5, watched: 6, transcript: 7,
};

const H = 3600000;
const IST = 5.5 * H;

/** Go back `hours` from `end`, but only count weekday hours (IST).
 *  Markets are shut on Saturday and Sunday, so "24h" checked on a Sunday
 *  evening should still show Friday's filings, not an empty screen. */
function backWeekdayHours(end: number, hours: number): number {
  let t = end;
  let left = hours * H;
  while (left > 0) {
    const d = new Date(t - 1 + IST);
    const dayStart = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - IST;
    const weekend = d.getUTCDay() === 0 || d.getUTCDay() === 6;
    if (!weekend) {
      const span = t - dayStart;
      if (span >= left) return t - left;
      left -= span;
    }
    t = dayStart;
  }
  return t;
}

export function windowStart(w: Win, asOf: string): number {
  const end = new Date(asOf).getTime();
  switch (w.key) {
    case "24h": return backWeekdayHours(end, 24);
    case "3d": return backWeekdayHours(end, 72);
    case "7d": return end - 168 * H;
    case "14d": return end - 336 * H;
    case "custom": return w.from ? new Date(w.from + "T00:00:00+05:30").getTime() : backWeekdayHours(end, 24);
  }
}

/** When a short window had to reach past a weekend, say so, so nobody wonders
 *  why "24h" shows Friday's filings. */
export function windowNote(w: Win, asOf: string): string | null {
  const plain = { "24h": 24, "3d": 72 } as Record<string, number>;
  if (!(w.key in plain)) return null;
  const end = new Date(asOf).getTime();
  const start = windowStart(w, asOf);
  if (end - start <= plain[w.key] * H) return null;
  const from = new Date(start).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  });
  return `Weekend hours don't count, so this covers ${from} to now.`;
}

function windowEnd(w: Win, asOf: string): number {
  if (w.key === "custom" && w.to) return new Date(w.to + "T23:59:59+05:30").getTime();
  return new Date(asOf).getTime();
}

export function inWindow(f: Filing, w: Win, asOf: string): boolean {
  if (!f.time) return false;
  const t = new Date(f.time).getTime();
  return t >= windowStart(w, asOf) && t <= windowEnd(w, asOf);
}

export function thresholds(s: Settings, symbol: string) {
  const o = s.overrides[symbol] || {};
  return { vm: o.volume_multiple ?? s.volume_multiple, mp: o.move_pct ?? s.move_pct };
}

/** Price/volume breaches in the window. The latest session is always included,
 *  so Monday morning still shows Friday's moves. */
export function moves(prices: Record<string, PriceStock>, filings: Filing[], s: Settings, w: Win, asOf: string): Move[] {
  const fromDate = istDate(new Date(windowStart(w, asOf)).toISOString());
  const toDate = istDate(new Date(windowEnd(w, asOf)).toISOString());
  const out: Move[] = [];
  for (const st of Object.values(prices)) {
    const { vm, mp } = thresholds(s, st.symbol);
    const series = st.series;
    series.forEach((d, i) => {
      const latest = i === series.length - 1;
      if (!(latest || (d.date >= fromDate && d.date <= toDate))) return;
      const why: ("volume" | "move")[] = [];
      if (d.vol_multiple !== null && d.vol_multiple >= vm) why.push("volume");
      if (d.change_pct !== null && Math.abs(d.change_pct) >= mp) why.push("move");
      if (!why.length) return;
      const prev = i > 0 ? series[i - 1].date : d.date;
      const explainedBy =
        filings.find((f) => f.symbol === st.symbol && f.material && f.time && istDate(f.time) >= prev && istDate(f.time) <= d.date) || null;
      out.push({ symbol: st.symbol, date: d.date, change_pct: d.change_pct, vol_multiple: d.vol_multiple, why, explainedBy, series: series.slice(Math.max(0, i - 19), i + 1) });
    });
  }
  return out;
}

export type PillarState = "holding" | "risk" | "broken" | "unknown";

const BAND: Record<string, number> = { revenue_yoy: 2, pat_yoy: 2, ebitda_margin: 0.5, pat_margin: 0.5, cfo_to_pat: 0.05 };

export function checkMetric(p: Pillar, v: number | null | undefined): PillarState {
  if (v === null || v === undefined || p.value === undefined) return "unknown";
  const ok = p.op === "<=" ? v <= p.value : v >= p.value;
  if (!ok) return "broken";
  const band = BAND[p.metric || ""] ?? 0;
  const near = p.op === "<=" ? v > p.value - band : v < p.value + band;
  return near ? "risk" : "holding";
}

export const METRIC_LABEL: Record<string, string> = {
  revenue_yoy: "Revenue growth YoY", pat_yoy: "PAT growth YoY", ebitda_margin: "EBITDA margin",
  pat_margin: "PAT margin", cfo_to_pat: "Cash from ops ÷ PAT",
};

export function fmtMetric(metric: string, v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return metric === "cfo_to_pat" ? `${v.toFixed(2)}×` : `${v.toFixed(1)}%`;
}

/** Holdings screen: where each pillar stands right now. */
export function pillarState(p: Pillar, h: Holding | undefined, filings: Filing[], asOf: string, lookbackDays: number) {
  if (p.type === "event") {
    const hit = filings.find((f) => f.symbol === h?.symbol && f.category === p.category && f.time &&
      new Date(f.time).getTime() >= new Date(asOf).getTime() - lookbackDays * 86400000);
    return { state: (hit ? "risk" : "holding") as PillarState, value: null, detail: hit ? `${CATEGORY_LABEL[p.category!]} filing on ${istDate(hit.time!)}` : `No ${CATEGORY_LABEL[p.category!]?.toLowerCase()} filings in the last ${lookbackDays} days`, filing: hit || null };
  }
  const v = h?.metrics?.[p.metric as keyof Holding["metrics"]] as number | null | undefined;
  const period = p.metric === "cfo_to_pat" ? h?.metrics?.cfo_to_pat_year : h?.metrics?.quarter;
  return { state: checkMetric(p, v), value: v ?? null, detail: `${METRIC_LABEL[p.metric!]} ${fmtMetric(p.metric!, v)}${period ? ` (${period})` : ""} vs ${p.op} ${fmtMetric(p.metric!, p.value)}`, filing: null };
}

function cardValue(f: Filing, metric: string): number | null | undefined {
  const c = f.results_card;
  if (!c?.available) return undefined;
  const m = (k: string) => c.metrics?.find((x) => x.key === k);
  switch (metric) {
    case "revenue_yoy": return m("revenue")?.yoy;
    case "pat_yoy": return m("pat")?.yoy;
    case "ebitda_margin": return c.margins?.[0]?.value;
    case "pat_margin": return c.margins?.[1]?.value;
    default: return undefined;
  }
}

export function reasonsFor(f: Filing, s: Settings): Reason[] {
  const r: Reason[] = [];
  const pillars = s.pillars[f.symbol] || [];
  for (const p of pillars) {
    if (p.type === "event" && p.category === f.category && f.material) {
      r.push({ kind: "pillar-risk", text: `Pillar at risk: ${p.label}` });
    }
    if (p.type === "metric" && f.category === "results" && f.results_card?.available) {
      const v = cardValue(f, p.metric!);
      const st = checkMetric(p, v);
      if (st === "broken") r.push({ kind: "pillar-broken", text: `Pillar broken: ${p.label} (${fmtMetric(p.metric!, v)})` });
      else if (st === "risk") r.push({ kind: "pillar-risk", text: `Pillar close to the line: ${p.label} (${fmtMetric(p.metric!, v)})` });
      else if (st === "holding") r.push({ kind: "pillar-holds", text: `Pillar holds: ${p.label}` });
    }
  }
  const L = f.promise_links || {};
  if (L.orphaned) r.push({ kind: "orphan", text: `${L.orphaned} open promise${L.orphaned > 1 ? "s" : ""} lose their owner` });
  if (L.settles) r.push({ kind: "promise", text: `Settles ${L.settles} promise${L.settles > 1 ? "s" : ""}` });
  if (L.ledger_updated) r.push({ kind: "transcript", text: "Promise ledger updated" });
  if (f.material && s.watched.includes(f.category) && !r.some((x) => x.kind !== "transcript")) {
    r.push({ kind: "watched", text: `You watch ${CATEGORY_LABEL[f.category].toLowerCase()}` });
  }
  return r.sort((a, b) => RANK[a.kind] - RANK[b.kind]);
}

export interface Digest {
  tier1: Entry[]; tier2: FilingEntry[]; tier3: Filing[]; scanned: number; moves: Move[];
}

export function buildDigest(filings: Filing[], prices: Record<string, PriceStock>, s: Settings, w: Win, asOf: string): Digest {
  const inW = filings.filter((f) => inWindow(f, w, asOf));
  const mv = moves(prices, filings, s, w, asOf);
  const entries: FilingEntry[] = inW.map((f) => {
    const reasons = reasonsFor(f, s);
    const touches = reasons.some((x) => x.kind !== "transcript");
    const tier: 1 | 2 | 3 = !f.material ? 3 : touches ? 1 : 2;
    const reaction = mv.filter((m) => m.explainedBy?.id === f.id).sort((a, b) => (a.date < b.date ? 1 : -1))[0] || null;
    return { kind: "filing", filing: f, tier, reasons, reaction };
  });
  // a move explained by a filing that's outside the window still counts as explained
  const unexplained: MoveEntry[] = mv
    .filter((m) => !m.explainedBy)
    .map((m) => ({ kind: "move", move: m, tier: 1, reasons: [{ kind: "unexplained", text: "No filing explains this move" }] }));
  const t1: Entry[] = [...entries.filter((e) => e.tier === 1), ...unexplained];
  const score = (e: Entry) => Math.min(...e.reasons.map((r) => RANK[r.kind]), 9);
  const time = (e: Entry) => (e.kind === "filing" ? e.filing.time || "" : e.move.date + "T15:30");
  t1.sort((a, b) => score(a) - score(b) || (time(a) < time(b) ? 1 : -1));
  return {
    tier1: t1,
    tier2: entries.filter((e) => e.tier === 2),
    tier3: entries.filter((e) => e.tier === 3).map((e) => e.filing),
    scanned: inW.length,
    moves: mv,
  };
}

// Shapes of the JSON the pipeline writes into public/data. See docs/schemas.md.

export type Category =
  | "results" | "M&A" | "fund_raise" | "management_change" | "litigation" | "insider_trading"
  | "earnings_call" | "investor_meetings" | "credit_rating" | "dividend" | "bonus_split" | "capex"
  | "press_release" | "postal_ballot" | "agm_egm" | "pledging" | "unclassified";

export interface Metric { key: string; label: string; value: number | null; qoq: number | null; yoy: number | null; note?: string | null }
export interface Margin { label: string; value: number | null; qoq_pp: number | null; yoy_pp: number | null }
export interface Settled { id: string; metric: string; target: string; status: string; actual: string; speaker: string }

export interface ResultsCard {
  symbol: string; quarter: string; available: boolean; note?: string; lender?: boolean;
  source?: "screener" | "filing"; basis?: string; source_url?: string; filing_url?: string | null;
  metrics?: Metric[]; margins?: Margin[];
  check?: { pat_filing: number; pat_screener: number; diff_pct: number; mismatch: boolean } | null;
  settles?: Settled[];
}

export interface Orphan { id: string; metric: string; target: string; deadline: string; quote: string; page: number; transcript_url: string; said: string }
export interface PersonChange {
  name: string; role: string; change: "joining" | "leaving" | "other"; effective_date?: string | null;
  bio?: { text: string; source: "filing" | "web"; links: { title: string; url: string }[] } | null;
  orphaned_promises?: Orphan[];
}

export interface Filing {
  id: string; symbol: string; company: string; time: string | null; exchange_category: string; subject: string;
  url: string | null; source: "nse" | "bse"; category: Category; material: boolean; rule: string; classified_by: string;
  summary?: string | null; results_card?: ResultsCard | null;
  management?: { people: PersonChange[]; has_ledger: boolean } | null;
  promise_links: { settles?: number; orphaned?: number; ledger_updated?: boolean };
}

export interface Session { date: string; close: number | null; change_pct: number | null; volume: number; avg_vol_20: number | null; vol_multiple: number | null }
export interface PriceStock { symbol: string; yahoo: string; series: Session[]; last: Session | null }

export interface Pillar {
  id: string; label: string; type: "metric" | "event";
  metric?: "revenue_yoy" | "pat_yoy" | "ebitda_margin" | "pat_margin" | "cfo_to_pat"; op?: ">=" | "<="; value?: number;
  category?: Category;
}

export interface Holding {
  symbol: string; name: string; sector: string; company_type: string; last: Session | null; spark: number[];
  metrics: { quarter?: string; revenue_yoy?: number | null; pat_yoy?: number | null; ebitda_margin?: number | null; pat_margin?: number | null; cfo_to_pat?: number | null; cfo_to_pat_year?: string };
  credibility?: { kept: number; missed: number; settled: number; score: number | null } | null;
  ledger_counts?: Record<string, number> | null; has_research: boolean;
}

export interface Meta {
  as_of: string; sample: boolean; lookback_days: number;
  classify: { total?: number; by_rules?: number; by_model?: number; fallback?: number; material?: number };
  cost: { total: { calls: number; cache_hits: number; inr: number; in_tok: number; out_tok: number }; by_step: Record<string, { calls: number; cache_hits: number; inr: number; tokens: number; model: string }> };
  models: Record<string, string>; failed_prices: string[];
}

export interface Config {
  holdings: { symbol: string; sector: string; name: string }[];
  research: { symbol: string; name: string }[];
  alerts: { volume_multiple: number; move_pct: number; overrides: Record<string, { volume_multiple?: number; move_pct?: number }> };
  watched_categories: Category[]; pillars: Record<string, Pillar[]>; categories: Category[];
}

export interface Mention { quarter_said: string; call_date: string; target_text: string; speaker_name: string; speaker_role: string; verbatim_quote: string; page: number; transcript_url: string }
export interface Thread {
  id: string; metric: string; metric_key: string; unit: string; deadline: string; target_text: string;
  first_said: string; times_said: number; revised: boolean; revision_direction: "up" | "down" | null; quietly_dropped: boolean;
  speakers: string[]; mentions: Mention[]; status: string; display_status: string; actual_text?: string; reason?: string; progress?: string; settled_by?: string;
}
export interface Ledger {
  symbol?: string; company?: string; threads: Thread[]; summary: string; note?: string;
  credibility: { kept?: number; missed?: number; settled?: number; score?: number | null };
  counts: Record<string, number>;
  transcripts: { date_label: string; quarter: string; url: string; readable: boolean; pages?: number }[];
  stats?: { tokens_full: number; tokens_sent: number; extracted: number; dropped_quote_not_found: number };
}

export interface Tile { label: string; value: number | null; unit: string; delta?: number | null; delta_label?: string; note?: string | null }

export interface Company {
  symbol: string; company: string; as_of: string; view: string; company_type: string; screener_url: string; about: string;
  ledger: Ledger;
  guidance: { id: string; metric: string; target: string; deadline: string; status: string; progress: string; said_by: string; said: string; quote: string; page: number; transcript_url: string }[];
  financial_snapshot: { quarter?: string; tiles?: Tile[]; source?: string };
  trajectory: { years: { fy: string; revenue: number; ebitda: number | null; margin: number | null; pat: number | null }[]; quarters: { q: string; revenue: number; margin: number | null; pat: number | null }[]; headline: { label: string; value: number; unit: string; tone: string }[]; source: string };
  balance_sheet: { years: { fy: string; borrowings: number | null; equity: number | null; de: number | null; wc_days: number | null; ccc: number | null; debtor_days: number | null; cwip: number | null }[]; note: string | null; source: string };
  cash_quality: { years: { fy: string; cfo: number; pat: number; ratio: number | null; after_investing: number | null }[]; five_year_ratio: number | null; verdict: string | null; lender: boolean; source: string };
  business: { what_they_do: string; page: number; segments: { name: string; detail: string; page: number }[]; revenue_mix?: string | null; mix_page?: number | null; source: string; transcript_url: string } | null;
  bull_bear: { bull: { text: string; source: string }[]; bear: { text: string; source: string }[]; pillars: { pillar_id: string; bear: string; would_prove_wrong: string; source: string; supported: boolean }[] } | null;
  pillars: Pillar[];
  sources: { screener: string; transcripts: { label: string; url: string }[]; annual_reports: { label: string; url: string }[] };
}

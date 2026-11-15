"use client";

import { useState } from "react";
import type { Company, Thread } from "@/lib/types";
import { cr, num, pct, pp, tone } from "@/lib/format";
import { Card, Chip, Cite, ExtLink, Notice, SectionTitle, Sheet, Status } from "./ui";
import type { QuoteOpen } from "./cards";

// ---------------------------------------------------------------- promises

const FILTERS = ["all", "missed", "dropped", "revised", "pending", "kept", "unverifiable"] as const;

function threadLine(t: Thread): string {
  if (t.display_status === "revised" && t.mentions.length > 1) {
    const a = t.mentions[0].target_text, b = t.mentions[t.mentions.length - 1].target_text;
    return `${t.revision_direction === "down" ? "Cut" : "Raised"} from ${a} to ${b}`;
  }
  if (t.display_status === "dropped") {
    return `Last said in ${t.mentions[t.mentions.length - 1].quarter_said}; not mentioned in the last two calls`;
  }
  if (t.actual_text) return `Promised ${t.target_text} · delivered ${t.actual_text}`;
  if (t.progress) return `Promised ${t.target_text} · so far ${t.progress.split(": ")[1] ?? t.progress}`;
  return `Promised ${t.target_text}`;
}

export function Scoreboard({ c }: { c: Company }) {
  const L = c.ledger;
  const [f, setF] = useState<(typeof FILTERS)[number]>("all");
  const [hist, setHist] = useState<Thread | null>(null);
  if (!L.threads.length) {
    return <Notice>{L.note || "No dated promises found in the last four earnings calls."}</Notice>;
  }
  const order = { missed: 0, dropped: 1, revised: 2, pending: 3, kept: 4, unverifiable: 5 } as Record<string, number>;
  const shown = L.threads.filter((t) => f === "all" || t.display_status === f).sort((a, b) => (order[a.display_status] ?? 9) - (order[b.display_status] ?? 9));
  const cred = L.credibility;
  const s = L.stats;
  return (
    <div>
      <Card className="p-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="num text-[30px] font-semibold leading-none tracking-tight">
              {cred.kept ?? 0}<span className="text-ink-3"> of {cred.settled ?? 0}</span>
            </div>
            <div className="mt-1.5 text-[12.5px] text-ink-2">promises that fell due were kept</div>
          </div>
          <div className="text-right text-[12px] text-ink-3">
            {cred.score === null || cred.score === undefined ? "Too few settled to score" : `Credibility ${Math.round(cred.score * 100)}%`}
          </div>
        </div>
        {(cred.settled ?? 0) > 0 && (
          <div className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div className="bg-up" style={{ width: `${((cred.kept ?? 0) / (cred.settled ?? 1)) * 100}%` }} />
            <div className="bg-down" style={{ width: `${((cred.missed ?? 0) / (cred.settled ?? 1)) * 100}%` }} />
          </div>
        )}
        {L.summary && (
          <p className="mt-4 border-t border-line pt-3 text-[13.5px] leading-relaxed">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">Narrative vs numbers</span>
            {L.summary}
          </p>
        )}
      </Card>

      <div className="no-scrollbar -mx-4 mt-3 flex gap-2 overflow-x-auto px-4">
        {FILTERS.filter((x) => x === "all" || (L.counts[x] ?? 0) > 0).map((x) => (
          <Chip key={x} active={f === x} onClick={() => setF(x)}>
            {x === "all" ? `All ${L.threads.length}` : `${x === "unverifiable" ? "Can't check" : x[0].toUpperCase() + x.slice(1)} ${L.counts[x]}`}
          </Chip>
        ))}
      </div>

      <div className="mt-3 space-y-2">
        {shown.map((t) => (
          <div key={t.id} className={`rounded-xl border px-3.5 py-3 ${t.display_status === "dropped" ? "border-dashed border-accent/60" : "border-line bg-surface"}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Status status={t.display_status} />
                <span className="truncate text-[14px] font-semibold">{t.metric}</span>
              </div>
              <span className="shrink-0 text-[12px] text-ink-3">by {t.deadline}</span>
            </div>
            <div className="num mt-1.5 text-[13px] text-ink-2">{threadLine(t)}</div>
            {t.reason && t.settled_by === "model" && <div className="mt-1 text-[12.5px] text-ink-3">{t.reason}</div>}
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="truncate text-[12px] text-ink-3">
                {t.speakers.join(", ")} · said {t.times_said}× since {t.first_said}
              </span>
              <Cite label={`${t.mentions.length > 1 ? `${t.mentions.length} quotes` : `p.${t.mentions[0].page}`}`} onClick={() => setHist(t)} />
            </div>
          </div>
        ))}
      </div>

      {s && (
        <p className="num mt-3 text-[11.5px] leading-relaxed text-ink-3">
          Read {L.transcripts.filter((t) => t.readable).length} transcripts. Sent the model only management&apos;s forward-looking lines
          ({s.tokens_full ? Math.round((s.tokens_sent / s.tokens_full) * 100) : 0}% of the text). {s.dropped_quote_not_found} extracted quotes were thrown away because they weren&apos;t on the page.
        </p>
      )}

      <Sheet open={!!hist} onClose={() => setHist(null)} title={hist?.metric || ""}>
        {hist && (
          <ol className="space-y-4">
            {hist.mentions.map((m, i) => (
              <li key={i} className="relative border-l border-line-2 pl-4">
                <span className="absolute -left-[4.5px] top-1 size-2 rounded-full bg-accent" />
                <div className="text-[12px] font-medium text-ink-2">
                  {m.quarter_said} call · {m.speaker_name}
                  {m.speaker_role ? `, ${m.speaker_role}` : ""} · target {m.target_text}
                </div>
                <blockquote className="mt-1 text-[14px] leading-relaxed">&ldquo;{m.verbatim_quote}&rdquo;</blockquote>
                <ExtLink href={`${m.transcript_url}#page=${m.page}`} className="mt-1 text-[12px]">page {m.page}</ExtLink>
              </li>
            ))}
          </ol>
        )}
      </Sheet>
    </div>
  );
}

// ---------------------------------------------------------------- guidance

export function Guidance({ c, onQuote }: { c: Company; onQuote: (q: QuoteOpen) => void }) {
  if (!c.guidance.length) return <Notice>No open guidance in the last four calls.</Notice>;
  return (
    <Card className="divide-y divide-line px-4">
      {c.guidance.map((g) => (
        <div key={g.id} className="py-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[13.5px] font-semibold">{g.metric}</span>
            <span className="num shrink-0 text-[13px]">{g.target} <span className="text-ink-3">by {g.deadline}</span></span>
          </div>
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-ink-2">
              {g.progress ? <span className="num">{g.progress} · </span> : null}
              {g.status !== "pending" ? <span className="text-accent">{g.status} · </span> : null}
              {g.said_by}
            </span>
            <Cite label={`${g.said} p.${g.page}`} onClick={() => onQuote({ title: g.metric, quote: g.quote, page: g.page, url: g.transcript_url, meta: `${g.said} earnings call, ${g.said_by}` })} />
          </div>
        </div>
      ))}
    </Card>
  );
}

// ---------------------------------------------------------------- numbers

export function Snapshot({ c }: { c: Company }) {
  const s = c.financial_snapshot;
  if (!s.tiles) return <Notice>No numbers.</Notice>;
  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        {s.tiles.map((t) => (
          <Card key={t.label} className="px-3.5 py-3">
            <div className="text-[11.5px] text-ink-3">{t.label}</div>
            <div className="num mt-1 text-[17px] font-semibold tracking-tight">
              {t.value === null ? "–" : t.unit === "cr" ? cr(t.value) : t.unit === "%" ? `${num(t.value, 1)}%` : `${num(t.value, 2)}×`}
              {t.unit === "cr" && t.value !== null && <span className="text-[12px] font-normal text-ink-3"> cr</span>}
            </div>
            {t.delta !== null && t.delta !== undefined && (
              <div className={`num text-[12px] ${tone(t.delta)}`}>
                {t.unit === "%" ? pp(t.delta) : pct(t.delta)} {t.delta_label?.replace("pp ", "")}
              </div>
            )}
            {t.note && <div className="text-[11.5px] text-ink-3">{t.note}</div>}
          </Card>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] text-ink-3">Source: {s.source}</p>
    </div>
  );
}

export function Trajectory({ c }: { c: Company }) {
  const t = c.trajectory;
  if (!t.years.length) return <Notice>No multi-year numbers.</Notice>;
  const max = Math.max(...t.years.map((y) => y.revenue));
  return (
    <div>
      {t.headline.length > 0 && (
        <div className="mb-3 grid grid-cols-3 gap-2">
          {t.headline.map((h) => (
            <div key={h.label} className="rounded-lg bg-surface-2 px-2.5 py-2">
              <div className="text-[11px] leading-tight text-ink-3">{h.label}</div>
              <div className={`num mt-1 text-[15px] font-semibold ${h.tone === "up" ? "text-up" : h.tone === "down" ? "text-down" : "text-ink"}`}>
                {h.unit === "pp" ? pp(h.value) : pct(h.value)}
              </div>
            </div>
          ))}
        </div>
      )}
      <Card className="px-3 pb-3 pt-4">
        <div className="text-[11.5px] text-ink-3">Revenue (₹ cr) and EBITDA margin, by year</div>
        <div className="mt-3 flex h-32 items-end gap-2">
          {t.years.map((y) => (
            <div key={y.fy} className="flex flex-1 flex-col items-center justify-end gap-1">
              <span className="num text-[10.5px] text-ink-3">{y.revenue >= 10000 ? `${(y.revenue / 1000).toFixed(0)}k` : num(y.revenue)}</span>
              <div className="w-full rounded-t bg-ink/80" style={{ height: `${(y.revenue / max) * 88}px` }} />
            </div>
          ))}
        </div>
        <div className="mt-1.5 flex gap-2">
          {t.years.map((y) => (
            <div key={y.fy} className="flex-1 text-center">
              <div className="text-[11px] text-ink-3">{y.fy}</div>
              <div className="num text-[11.5px] font-medium text-ink-2">{y.margin !== null ? `${y.margin}%` : "–"}</div>
            </div>
          ))}
        </div>
      </Card>
      <p className="mt-2 text-[11.5px] text-ink-3">Source: {t.source}</p>
    </div>
  );
}

export function BalanceSheet({ c }: { c: Company }) {
  const b = c.balance_sheet;
  if (!b.years.length) return <Notice>No balance sheet numbers.</Notice>;
  return (
    <div>
      <Card className="overflow-x-auto px-3 py-2">
        <table className="num w-full text-[12.5px]">
          <thead>
            <tr className="text-[11px] text-ink-3">
              <th className="py-1.5 text-left font-medium">Year</th>
              <th className="py-1.5 text-right font-medium">Debt ₹cr</th>
              <th className="py-1.5 text-right font-medium">Equity ₹cr</th>
              <th className="py-1.5 text-right font-medium">D/E</th>
              <th className="py-1.5 text-right font-medium">Cash cycle</th>
            </tr>
          </thead>
          <tbody>
            {b.years.map((y) => (
              <tr key={y.fy} className="border-t border-line">
                <td className="py-1.5 text-ink-2">{y.fy}</td>
                <td className="py-1.5 text-right">{num(y.borrowings)}</td>
                <td className="py-1.5 text-right">{num(y.equity)}</td>
                <td className="py-1.5 text-right">{c.company_type === "lender" ? "–" : y.de?.toFixed(2) ?? "–"}</td>
                <td className="py-1.5 text-right">{y.ccc !== null ? `${num(y.ccc)}d` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {b.note && <p className="mt-2 text-[13px] text-ink-2">{b.note}</p>}
      <p className="mt-2 text-[11.5px] text-ink-3">Source: {b.source}</p>
    </div>
  );
}

export function CashQuality({ c }: { c: Company }) {
  const q = c.cash_quality;
  if (!q.years.length) return <Notice>No cash flow numbers.</Notice>;
  const max = Math.max(...q.years.flatMap((y) => [Math.abs(y.cfo), Math.abs(y.pat)]));
  return (
    <div>
      {q.verdict && (
        <p className="mb-3 text-[14px] font-medium">
          {q.verdict}{" "}
          {q.five_year_ratio !== null && <span className="num font-normal text-ink-2">5-year cash from operations ÷ profit = {q.five_year_ratio.toFixed(2)}×</span>}
        </p>
      )}
      {q.lender && <p className="mb-3 text-[12.5px] text-ink-3">For a lender, operating cash flow mostly tracks loan growth, so read this loosely.</p>}
      <Card className="space-y-2 px-4 py-3">
        <div className="flex gap-4 text-[11px] text-ink-3">
          <span className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-ink" />Cash from ops</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-ink-3" />PAT</span>
        </div>
        {q.years.map((y) => (
          <div key={y.fy} className="grid grid-cols-[44px_1fr_44px] items-center gap-2">
            <span className="text-[11.5px] text-ink-3">{y.fy}</span>
            <div className="space-y-0.5">
              <div className={`h-2 rounded-sm ${y.cfo < 0 ? "bg-down" : "bg-ink"}`} style={{ width: `${(Math.abs(y.cfo) / max) * 100}%` }} />
              <div className="h-2 rounded-sm bg-ink-3" style={{ width: `${(Math.abs(y.pat) / max) * 100}%` }} />
            </div>
            <span className={`num text-right text-[12px] ${y.ratio !== null && y.ratio < 0.6 ? "text-down" : "text-ink-2"}`}>{y.ratio !== null ? `${y.ratio.toFixed(2)}×` : "–"}</span>
          </div>
        ))}
      </Card>
      <p className="mt-2 text-[11.5px] text-ink-3">Source: {q.source}</p>
    </div>
  );
}

// ---------------------------------------------------------------- words

export function Business({ c, onQuote }: { c: Company; onQuote: (q: QuoteOpen) => void }) {
  const b = c.business;
  if (!b) return <Notice>{c.about ? c.about : "Not enough in the latest transcript to describe the business."}</Notice>;
  const open = (page: number, text: string) => onQuote({ title: c.company, quote: text, page, url: b.transcript_url, meta: b.source });
  return (
    <Card className="space-y-3 p-4">
      <p className="text-[14px] leading-relaxed">
        {b.what_they_do} <Cite label={`p.${b.page}`} onClick={() => open(b.page, b.what_they_do)} />
      </p>
      {b.segments.length > 0 && (
        <div className="divide-y divide-line border-t border-line">
          {b.segments.map((s) => (
            <div key={s.name} className="flex items-start justify-between gap-3 py-2">
              <div>
                <div className="text-[13px] font-semibold">{s.name}</div>
                <div className="text-[12.5px] text-ink-2">{s.detail}</div>
              </div>
              <Cite label={`p.${s.page}`} onClick={() => open(s.page, `${s.name}: ${s.detail}`)} />
            </div>
          ))}
        </div>
      )}
      {b.revenue_mix && <p className="text-[12.5px] text-ink-2">Revenue mix: {b.revenue_mix}</p>}
      <p className="text-[11.5px] text-ink-3">From management&apos;s remarks on the {b.source}. Model-summarised, page-cited.</p>
    </Card>
  );
}

export function BullBear({ c }: { c: Company }) {
  const bb = c.bull_bear;
  if (!bb) return <Notice>Bull and bear cases need a model key and transcripts.</Notice>;
  const label = (id: string) => c.pillars.find((p) => p.id === id)?.label || id;
  return (
    <div className="space-y-3">
      {bb.pillars.length > 0 && (
        <Card accent className="p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-accent">Red-team my pillars</div>
          <div className="mt-2 divide-y divide-line">
            {bb.pillars.map((p) => (
              <div key={p.pillar_id} className="py-2.5">
                <div className="text-[13.5px] font-semibold">{label(p.pillar_id)}</div>
                <p className="mt-0.5 text-[13px] leading-snug">{p.bear}</p>
                {p.supported && <p className="mt-1 text-[12.5px] text-ink-2">Proved wrong if: {p.would_prove_wrong}</p>}
                <p className="mt-0.5 text-[11.5px] text-ink-3">{p.source}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
      {(["bull", "bear"] as const).map((side) => (
        <Card key={side} className="p-4">
          <div className={`text-[11px] font-semibold uppercase tracking-wide ${side === "bull" ? "text-up" : "text-down"}`}>{side === "bull" ? "Bull case" : "Bear case"}</div>
          <ul className="mt-2 space-y-2">
            {bb[side].map((x, i) => (
              <li key={i} className="text-[13.5px] leading-snug">
                {x.text} <span className="text-[11.5px] text-ink-3">· {x.source}</span>
              </li>
            ))}
          </ul>
        </Card>
      ))}
      <p className="text-[11.5px] text-ink-3">Written by the strong model from the numbers, the promise ledger and management quotes only. No news or broker views.</p>
    </div>
  );
}

export function Sources({ c }: { c: Company }) {
  return (
    <div className="space-y-1.5 text-[13px]">
      <div><ExtLink href={c.sources.screener}>screener.in ({c.view})</ExtLink></div>
      {c.sources.transcripts.map((t) => <div key={t.url}><ExtLink href={t.url}>{t.label} transcript</ExtLink></div>)}
      {c.sources.annual_reports.map((r) => <div key={r.url}><ExtLink href={r.url}>{r.label}</ExtLink></div>)}
    </div>
  );
}

export { SectionTitle };

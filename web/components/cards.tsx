"use client";

import { useState } from "react";
import Link from "next/link";
import type { FilingEntry, Move, MoveEntry, Reason } from "@/lib/engine";
import type { Filing, Orphan } from "@/lib/types";
import { CATEGORY_LABEL, cr, num, pct, pp, tone, when } from "@/lib/format";
import { Card, Cite, ExtLink, Icon, Sheet, Spark, Status, Tag } from "./ui";

export interface QuoteOpen { title: string; quote: string; page: number; url: string; meta: string }

function ReasonTags({ reasons }: { reasons: Reason[] }) {
  if (!reasons.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {reasons.map((r, i) => (
        <Tag key={i} tone={r.kind === "pillar-broken" || r.kind === "orphan" ? "down" : r.kind === "pillar-holds" ? "up" : r.kind === "watched" || r.kind === "transcript" ? "quiet" : "accent"}>
          {r.text}
        </Tag>
      ))}
    </div>
  );
}

function Head({ f, asOf, label }: { f: { symbol: string; company?: string; time?: string | null }; asOf: string; label: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <Link href={`/c/${f.symbol}`} className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-[15px] font-semibold tracking-tight">{f.symbol}</span>
          <span className="truncate text-[12.5px] text-ink-3">{f.company}</span>
        </div>
        <div className="mt-0.5 text-[12px] font-medium text-ink-2">{label}</div>
      </Link>
      {f.time && <span className="num shrink-0 pt-0.5 text-[12px] text-ink-3">{when(f.time, asOf)}</span>}
    </div>
  );
}

export function Reaction({ m }: { m: Move | null }) {
  if (!m) return null;
  return (
    <div className="num flex items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-ink-2">
      <span>Market on {new Date(m.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}:</span>
      <span className={`font-semibold ${tone(m.change_pct)}`}>{pct(m.change_pct)}</span>
      {m.vol_multiple !== null && <span>on {m.vol_multiple.toFixed(1)}× usual volume</span>}
    </div>
  );
}

export function ResultsBody({ f }: { f: Filing }) {
  const c = f.results_card;
  if (!c) return null;
  if (!c.available) return <p className="text-[13px] text-ink-2">{c.note}</p>;
  return (
    <div className="space-y-3">
      <table className="num w-full text-[13px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-wide text-ink-3">
            <th className="pb-1 text-left font-medium">₹ crore</th>
            <th className="pb-1 text-right font-medium">{c.quarter}</th>
            <th className="pb-1 text-right font-medium">QoQ</th>
            <th className="pb-1 text-right font-medium">YoY</th>
          </tr>
        </thead>
        <tbody>
          {c.metrics?.map((m) => (
            <tr key={m.key} className="border-t border-line">
              <td className="py-1.5 text-ink-2" title={m.note || undefined}>
                {m.label}
                {m.note && m.key !== "revenue" && <span className="ml-1 text-ink-3">*</span>}
              </td>
              <td className="py-1.5 text-right font-medium">{num(m.value)}</td>
              <td className={`py-1.5 text-right ${tone(m.qoq)}`}>{pct(m.qoq)}</td>
              <td className={`py-1.5 text-right ${tone(m.yoy)}`}>{pct(m.yoy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {c.margins && c.margins.length > 0 && (
        <div className="num flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
          {c.margins.map((m) => (
            <span key={m.label}>
              {m.label} <b className="font-semibold text-ink">{m.value ?? "–"}%</b>{" "}
              <span className={tone(m.yoy_pp)}>{pp(m.yoy_pp)} YoY</span>
            </span>
          ))}
        </div>
      )}
      {c.lender && <p className="text-[12px] text-ink-3">Lender: EBITDA doesn&apos;t apply, so the card shows financing profit instead.</p>}
      {!c.lender && <p className="text-[11.5px] text-ink-3">* EBITDA = operating profit before other income, as screener.in reports it.</p>}
      {c.check?.mismatch && (
        <p className="text-[12px] text-accent">PAT differs between the filing (₹{num(c.check.pat_filing)} cr) and screener.in (₹{num(c.check.pat_screener)} cr) by {c.check.diff_pct}%.</p>
      )}
      {c.settles && c.settles.length > 0 && (
        <div className="space-y-1.5 border-t border-line pt-2.5">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Promises due this quarter</div>
          {c.settles.map((s) => (
            <div key={s.id} className="flex items-start gap-2 text-[13px]">
              <Status status={s.status} />
              <div className="min-w-0">
                <span className="font-medium">{s.metric}</span>
                <span className="text-ink-2"> · promised {s.target}{s.actual ? `, delivered ${s.actual}` : ""}</span>
                <div className="text-[12px] text-ink-3">said by {s.speaker}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OrphanList({ items, onQuote }: { items: Orphan[]; onQuote: (q: QuoteOpen) => void }) {
  return (
    <div className="mt-2 space-y-1.5 rounded-lg border border-down/30 bg-down-soft px-3 py-2.5">
      <div className="text-[11.5px] font-semibold uppercase tracking-wide text-down">Promises this person made</div>
      {items.map((o) => (
        <div key={o.id} className="flex items-start justify-between gap-2 text-[13px]">
          <span>
            <b className="font-medium">{o.metric}</b> <span className="text-ink-2">{o.target} by {o.deadline}</span>
          </span>
          <Cite label={`${o.said} p.${o.page}`} onClick={() => onQuote({ title: o.metric, quote: o.quote, page: o.page, url: o.transcript_url, meta: `${o.said} earnings call` })} />
        </div>
      ))}
    </div>
  );
}

export function ManagementBody({ f, onQuote }: { f: Filing; onQuote: (q: QuoteOpen) => void }) {
  const m = f.management;
  if (!m || !m.people.length) return f.summary ? <p className="text-[13.5px]">{f.summary}</p> : null;
  return (
    <div className="space-y-3">
      {m.people.map((p, i) => (
        <div key={i} className={i ? "border-t border-line pt-3" : ""}>
          <div className="flex items-center gap-2">
            <Tag tone={p.change === "leaving" ? "down" : p.change === "joining" ? "up" : "quiet"}>{p.change === "leaving" ? "Leaving" : p.change === "joining" ? "Joining" : "Change"}</Tag>
            <span className="text-[14px] font-semibold">{p.name}</span>
          </div>
          <div className="mt-0.5 text-[12.5px] text-ink-2">
            {p.role}
            {p.effective_date ? ` · from ${p.effective_date}` : ""}
          </div>
          {p.change === "joining" && p.bio && (
            <div className="mt-2 text-[13px] leading-relaxed">
              {p.bio.text}
              <div className="mt-1 text-[11.5px] text-ink-3">
                {p.bio.source === "filing" ? "From the appointment filing" : "From public web results"}
                {p.bio.links.map((l) => (
                  <ExtLink key={l.url} href={l.url} className="ml-2">{new URL(l.url).hostname.replace("www.", "")}</ExtLink>
                ))}
              </div>
            </div>
          )}
          {p.change === "joining" && !p.bio && <div className="mt-1 text-[12.5px] text-ink-3">No profile in the filing.</div>}
          {p.change === "leaving" && p.orphaned_promises && p.orphaned_promises.length > 0 && <OrphanList items={p.orphaned_promises} onQuote={onQuote} />}
          {p.change === "leaving" && m.has_ledger && (!p.orphaned_promises || !p.orphaned_promises.length) && (
            <div className="mt-1 text-[12.5px] text-ink-3">No open promises in their name.</div>
          )}
        </div>
      ))}
    </div>
  );
}

export function FilingCard({ e, asOf, onQuote }: { e: FilingEntry; asOf: string; onQuote: (q: QuoteOpen) => void }) {
  const f = e.filing;
  const label =
    f.category === "results" && f.results_card?.quarter ? `Results · ${f.results_card.quarter}` : CATEGORY_LABEL[f.category];
  const urgent = e.reasons.some((r) => r.kind === "pillar-broken" || r.kind === "orphan");
  return (
    <Card accent={urgent} className="space-y-3 p-4">
      <Head f={f} asOf={asOf} label={label} />
      <ReasonTags reasons={e.reasons} />
      {f.category === "results" ? (
        <>
          {f.summary && <p className="text-[13.5px] leading-snug">{f.summary}</p>}
          <ResultsBody f={f} />
        </>
      ) : f.category === "management_change" ? (
        <ManagementBody f={f} onQuote={onQuote} />
      ) : (
        <p className="text-[13.5px] leading-snug">{f.summary || f.subject}</p>
      )}
      <Reaction m={e.reaction} />
      <div className="flex items-center justify-between text-[12px]">
        <ExtLink href={f.url}>{f.source.toUpperCase()} filing</ExtLink>
        {f.results_card?.source && <span className="text-ink-3">numbers: {f.results_card.source === "screener" ? "screener.in" : "filing PDF"}</span>}
      </div>
    </Card>
  );
}

export function MoveCard({ e, name }: { e: MoveEntry; name: string }) {
  const m = e.move;
  const d = new Date(m.date).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <Link href={`/c/${m.symbol}`} className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold tracking-tight">{m.symbol}</span>
            <span className="truncate text-[12.5px] text-ink-3">{name}</span>
          </div>
          <div className="mt-0.5 text-[12px] font-medium text-ink-2">Unexplained move · {d}</div>
        </Link>
        <Spark values={m.series.map((s) => s.close)} className="h-8 w-24 shrink-0" />
      </div>
      <div className="num mt-3 flex items-baseline gap-4">
        <span className={`text-[22px] font-semibold tracking-tight ${tone(m.change_pct)}`}>{pct(m.change_pct)}</span>
        {m.vol_multiple !== null && (
          <span className="text-[13px] text-ink-2">
            <b className={`font-semibold ${m.why.includes("volume") ? "text-accent" : "text-ink"}`}>{m.vol_multiple.toFixed(1)}×</b> usual volume
          </span>
        )}
      </div>
      <p className="mt-2 text-[13px] text-ink-2">No material filing on the day or the session before explains it. Worth a look.</p>
    </Card>
  );
}

export function Tier2Row({ e, asOf }: { e: FilingEntry; asOf: string }) {
  const f = e.filing;
  return (
    <div className="border-b border-line py-3 last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex min-w-0 items-baseline gap-2">
          <Link href={`/c/${f.symbol}`} className="text-[13.5px] font-semibold">{f.symbol}</Link>
          <span className="text-[12px] text-ink-3">{CATEGORY_LABEL[f.category]}</span>
        </div>
        <span className="num shrink-0 text-[12px] text-ink-3">{when(f.time, asOf)}</span>
      </div>
      <div className="mt-0.5 flex items-start justify-between gap-3">
        <p className="text-[13px] leading-snug text-ink-2">{f.summary || f.subject}</p>
        {f.url && (
          <a href={f.url} target="_blank" rel="noopener noreferrer" className="mt-0.5 shrink-0 text-ink-3 hover:text-ink" aria-label="Open filing">
            <Icon name="ext" className="size-4" />
          </a>
        )}
      </div>
      {e.reaction && <div className="mt-2"><Reaction m={e.reaction} /></div>}
    </div>
  );
}

export function RoutineGroup({ items }: { items: Filing[] }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  const groups = items.reduce<Record<string, Filing[]>>((g, f) => {
    (g[f.category] ||= []).push(f);
    return g;
  }, {});
  return (
    <div className="rounded-xl border border-line">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="text-[13.5px] text-ink-2">
          <b className="num font-semibold text-ink">{items.length}</b> routine filings
          <span className="text-ink-3"> · {Object.keys(groups).map((k) => CATEGORY_LABEL[k].toLowerCase()).slice(0, 3).join(", ")}{Object.keys(groups).length > 3 ? "…" : ""}</span>
        </span>
        <Icon name="down" className={`size-4 text-ink-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="border-t border-line px-4 pb-2">
          {Object.entries(groups).map(([cat, fs]) => (
            <div key={cat} className="py-2">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                {CATEGORY_LABEL[cat]} · {fs.length}
              </div>
              {fs.map((f) => (
                <a key={f.id} href={f.url || undefined} target="_blank" rel="noopener noreferrer" className="flex gap-2 py-1 text-[12.5px] text-ink-2 hover:text-ink">
                  <span className="w-[86px] shrink-0 font-medium text-ink">{f.symbol}</span>
                  <span className="truncate">{f.subject}</span>
                </a>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function QuoteSheet({ q, onClose }: { q: QuoteOpen | null; onClose: () => void }) {
  return (
    <Sheet open={!!q} onClose={onClose} title={q?.title || ""}>
      {q && (
        <div className="space-y-3">
          <blockquote className="border-l-2 border-accent pl-3 text-[14.5px] leading-relaxed">&ldquo;{q.quote}&rdquo;</blockquote>
          <div className="text-[12.5px] text-ink-3">
            {q.meta} · page {q.page}
          </div>
          <ExtLink href={q.url ? `${q.url}#page=${q.page}` : null} className="text-[13px]">Open the transcript at page {q.page}</ExtLink>
        </div>
      )}
    </Sheet>
  );
}

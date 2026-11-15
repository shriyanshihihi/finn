"use client";

import { useMemo, useState } from "react";
import { useStore } from "@/components/Providers";
import { FilingCard, MoveCard, QuoteSheet, RoutineGroup, Tier2Row, type QuoteOpen } from "@/components/cards";
import { Card, Chip, Notice, SectionTitle, Skeleton } from "@/components/ui";
import { buildDigest, windowNote, type Win, type WindowKey } from "@/lib/engine";
import { asOfLabel, istDate } from "@/lib/format";

const WINDOWS: { key: WindowKey; label: string }[] = [
  { key: "24h", label: "24h" },
  { key: "3d", label: "3 days" },
  { key: "7d", label: "7 days" },
  { key: "14d", label: "14 days" },
  { key: "custom", label: "Custom" },
];

export default function Today() {
  const { ready, error, meta, config, filings, prices, settings, update } = useStore();
  const [win, setWin] = useState<Win>({ key: "24h" });
  const [quote, setQuote] = useState<QuoteOpen | null>(null);

  const digest = useMemo(
    () => (meta && settings ? buildDigest(filings, prices, settings, win, meta.as_of) : null),
    [filings, prices, settings, win, meta],
  );
  const names = useMemo(() => Object.fromEntries((config?.holdings || []).map((h) => [h.symbol, h.name])), [config]);

  if (!ready) return <Skeleton />;
  if (error || !meta || !settings || !digest) return <div className="pt-10"><Notice>{error}</Notice></div>;

  const t1 = digest.tier1.length, t2 = digest.tier2.length, t3 = digest.tier3.length;
  const minDate = istDate(new Date(new Date(meta.as_of).getTime() - meta.lookback_days * 86400000).toISOString());
  const maxDate = istDate(meta.as_of);
  const st = meta.classify;
  const rulesShare = st.total ? Math.round(((st.by_rules || 0) / st.total) * 100) : null;

  return (
    <div>
      <header className="flex items-center justify-between pb-1 pt-5">
        <span className="text-[13px] font-bold tracking-[0.18em]">FINN</span>
        <span className="num text-[12px] text-ink-3">Data as of {asOfLabel(meta.as_of)}</span>
      </header>
      <h1 className="pt-3 text-[24px] font-semibold leading-tight tracking-tight">What changed in what you believe</h1>

      {meta.sample && (
        <div className="mt-3 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-[12.5px] text-accent">
          Sample data with made-up companies. Run the pipeline to load real filings.
        </div>
      )}

      {!settings.onboarded && (
        <Card className="mt-4 p-4">
          <p className="text-[13.5px] leading-relaxed text-ink-2">
            FINN only puts something at the top when it touches <b className="text-ink">why you own a stock</b> (your pillars) or
            <b className="text-ink"> what management promised</b>. Everything else gets one line or gets folded away.
          </p>
          <button onClick={() => update({ onboarded: true })} className="mt-3 text-[13px] font-semibold text-accent">Got it</button>
        </Card>
      )}

      <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4">
        {WINDOWS.filter((w) => w.key !== "14d" || meta.lookback_days >= 14).map((w) => (
          <Chip key={w.key} active={win.key === w.key} onClick={() => setWin(w.key === "custom" ? { key: "custom", from: minDate, to: maxDate } : { key: w.key })}>
            {w.label}
          </Chip>
        ))}
      </div>
      {windowNote(win, meta.as_of) && (
        <p className="mt-2 text-[12px] text-ink-3">{windowNote(win, meta.as_of)}</p>
      )}
      {win.key === "custom" && (
        <div className="mt-3 flex items-center gap-2 text-[13px] text-ink-2">
          <input type="date" min={minDate} max={maxDate} value={win.from} onChange={(e) => setWin({ ...win, from: e.target.value })}
            className="h-9 rounded-lg border border-line-2 bg-surface px-2 text-ink" />
          <span>to</span>
          <input type="date" min={minDate} max={maxDate} value={win.to} onChange={(e) => setWin({ ...win, to: e.target.value })}
            className="h-9 rounded-lg border border-line-2 bg-surface px-2 text-ink" />
        </div>
      )}

      <div className="num mt-4 flex gap-4 text-[13px] text-ink-2">
        <span><b className="text-[15px] font-semibold text-accent">{t1}</b> need you</span>
        <span><b className="text-[15px] font-semibold text-ink">{t2}</b> worth a line</span>
        <span><b className="text-[15px] font-semibold text-ink-3">{t3}</b> routine</span>
      </div>

      <SectionTitle aside="touches a pillar, a promise, or a category you watch">Moves a belief</SectionTitle>
      {t1 === 0 ? (
        <Notice>
          Nothing in this window touches your pillars or management&apos;s promises.
          {win.key === "24h" && <button className="ml-1 font-semibold text-accent" onClick={() => setWin({ key: "7d" })}>See the last 7 days</button>}
        </Notice>
      ) : (
        <div className="space-y-3">
          {digest.tier1.map((e) =>
            e.kind === "filing" ? (
              <FilingCard key={e.filing.id} e={e} asOf={meta.as_of} onQuote={setQuote} />
            ) : (
              <MoveCard key={`${e.move.symbol}-${e.move.date}`} e={e} name={names[e.move.symbol] || ""} />
            ),
          )}
        </div>
      )}

      {t2 > 0 && (
        <>
          <SectionTitle aside="material, but doesn't touch a belief">Worth a line</SectionTitle>
          <Card className="px-4">
            {digest.tier2.map((e) => <Tier2Row key={e.filing.id} e={e} asOf={meta.as_of} />)}
          </Card>
        </>
      )}

      {t3 > 0 && (
        <>
          <SectionTitle>Routine</SectionTitle>
          <RoutineGroup items={digest.tier3} />
        </>
      )}

      <div className="py-10 text-center">
        <div className="text-[15px] font-semibold">You&apos;re caught up</div>
        <div className="num mt-1 text-[13px] text-ink-3">
          {digest.scanned} filings and {Object.keys(prices).length} price charts checked · {t1 + t2} worth your time
        </div>
      </div>

      <footer className="num border-t border-line pt-3 text-[11.5px] leading-relaxed text-ink-3">
        This brief cost about ₹{meta.cost.total.inr.toFixed(2)} at paid model rates · {meta.cost.total.calls} model calls,{" "}
        {meta.cost.total.cache_hits} answered from cache
        {rulesShare !== null && <> · {rulesShare}% of filings sorted by rules with no model</>}.
      </footer>

      <QuoteSheet q={quote} onClose={() => setQuote(null)} />
    </div>
  );
}

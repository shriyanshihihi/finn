"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useStore } from "@/components/Providers";
import { Card, Icon, Notice, SectionTitle, Skeleton, Spark } from "@/components/ui";
import { pillarState, type PillarState } from "@/lib/engine";
import { pct, tone } from "@/lib/format";
import type { Holding, Pillar } from "@/lib/types";

const ORDER: Record<PillarState | "none", number> = { broken: 0, risk: 1, holding: 2, unknown: 3, none: 4 };
const DOT: Record<PillarState, string> = { holding: "bg-up", risk: "bg-accent", broken: "bg-down", unknown: "bg-ink-3" };
const WORD: Record<PillarState, string> = { holding: "Holding", risk: "At risk", broken: "Broken", unknown: "Can't check yet" };

export default function Holdings() {
  const { ready, error, meta, holdings, filings, settings } = useStore();
  const [open, setOpen] = useState<string | null>(null);

  const rows = useMemo(() => {
    if (!meta || !settings) return [];
    return holdings
      .map((h) => {
        const ps = (settings.pillars[h.symbol] || []).map((p) => ({ p, ...pillarState(p, h, filings, meta.as_of, meta.lookback_days) }));
        const worst = ps.length ? ps.reduce((w, x) => (ORDER[x.state] < ORDER[w] ? x.state : w), "unknown" as PillarState) : "none";
        return { h, ps, worst: worst as PillarState | "none" };
      })
      .sort((a, b) => ORDER[a.worst] - ORDER[b.worst] || a.h.symbol.localeCompare(b.h.symbol));
  }, [holdings, filings, settings, meta]);

  if (!ready) return <Skeleton />;
  if (error || !meta) return <div className="pt-10"><Notice>{error}</Notice></div>;

  const all = rows.flatMap((r) => r.ps);
  const count = (s: PillarState) => all.filter((x) => x.state === s).length;

  return (
    <div>
      <h1 className="pt-8 text-[24px] font-semibold tracking-tight">Holdings</h1>
      <p className="mt-1 text-[13.5px] text-ink-2">Why you own each stock, and whether that still holds.</p>
      <div className="num mt-4 flex gap-4 text-[13px] text-ink-2">
        <span><b className="text-[15px] font-semibold text-down">{count("broken")}</b> broken</span>
        <span><b className="text-[15px] font-semibold text-accent">{count("risk")}</b> at risk</span>
        <span><b className="text-[15px] font-semibold text-up">{count("holding")}</b> holding</span>
      </div>

      <SectionTitle aside={`${holdings.length} stocks · worst first`}>Your pillars</SectionTitle>
      <div className="space-y-2.5">
        {rows.map(({ h, ps }) => (
          <Row key={h.symbol} h={h} ps={ps} open={open === h.symbol} onToggle={() => setOpen(open === h.symbol ? null : h.symbol)} />
        ))}
      </div>
    </div>
  );
}

type PS = { p: Pillar; state: PillarState; value: number | null; detail: string };

function Row({ h, ps, open, onToggle }: { h: Holding; ps: PS[]; open: boolean; onToggle: () => void }) {
  const c = h.credibility;
  return (
    <Card className="overflow-hidden">
      <button onClick={onToggle} className="w-full px-4 py-3.5 text-left">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-[15px] font-semibold tracking-tight">{h.symbol}</span>
              <span className="truncate text-[12px] text-ink-3">{h.sector}</span>
            </div>
            <div className="truncate text-[12.5px] text-ink-3">{h.name}</div>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <Spark values={h.spark} className="h-7 w-16" />
            <div className="num text-right">
              <div className="text-[13.5px] font-medium">{h.last?.close?.toLocaleString("en-IN", { maximumFractionDigits: 1 }) ?? "–"}</div>
              <div className={`text-[12px] ${tone(h.last?.change_pct)}`}>{pct(h.last?.change_pct)}</div>
            </div>
          </div>
        </div>
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {ps.length === 0 && <span className="text-[12.5px] text-ink-3">No pillars yet</span>}
          {ps.map(({ p, state }) => (
            <span key={p.id} className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-2">
              <span className={`size-2 rounded-full ${DOT[state]}`} />
              {p.label}
            </span>
          ))}
        </div>
        {c && c.settled > 0 && (
          <div className="num mt-2 text-[12px] text-ink-3">
            Management kept <b className="text-ink-2">{c.kept} of {c.settled}</b> promises that fell due
          </div>
        )}
      </button>
      {open && (
        <div className="space-y-2.5 border-t border-line bg-surface-2/50 px-4 py-3">
          {ps.map(({ p, state, detail }) => (
            <div key={p.id} className="text-[13px]">
              <div className="flex items-center gap-2">
                <span className={`size-2 rounded-full ${DOT[state]}`} />
                <span className="font-medium">{p.label}</span>
                <span className="text-[12px] text-ink-3">{WORD[state]}</span>
              </div>
              <div className="num ml-4 text-[12.5px] text-ink-2">{detail}</div>
            </div>
          ))}
          {ps.length === 0 && (
            <div className="text-[13px] text-ink-2">
              Add the reasons you own {h.symbol} in <Link href="/settings#pillars" className="font-medium text-accent">Settings</Link>, and FINN will check every filing against them.
            </div>
          )}
          <Link href={h.has_research ? `/c/${h.symbol}` : `/research?s=${h.symbol}`} className="inline-flex items-center gap-1 pt-1 text-[13px] font-semibold text-accent">
            {h.has_research ? "Promises and research" : "Research it now"}
            <Icon name="chevron" className="size-4" />
          </Link>
        </div>
      )}
    </Card>
  );
}

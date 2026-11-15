"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { QuoteSheet, type QuoteOpen } from "@/components/cards";
import { BalanceSheet, BullBear, Business, CashQuality, Guidance, Scoreboard, Snapshot, Sources, Trajectory } from "@/components/company";
import { ExtLink, Icon, Notice, SectionTitle, Skeleton } from "@/components/ui";
import { getCompany } from "@/lib/data";
import { asOfLabel } from "@/lib/format";
import type { Company } from "@/lib/types";

const NAV = [
  ["promises", "Promises"],
  ["guidance", "Guidance"],
  ["snapshot", "Snapshot"],
  ["trajectory", "Trajectory"],
  ["balance", "Balance sheet"],
  ["cash", "Cash"],
  ["business", "Business"],
  ["bullbear", "Bull & bear"],
  ["sources", "Sources"],
];

export default function CompanyPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol || "").toUpperCase();
  const [c, setC] = useState<Company | null | undefined>(undefined);
  const [quote, setQuote] = useState<QuoteOpen | null>(null);

  useEffect(() => {
    setC(undefined);
    getCompany<Company>(symbol).then(setC);
  }, [symbol]);

  if (c === undefined) return <Skeleton />;
  if (c === null) {
    return (
      <div className="pt-8">
        <Back />
        <h1 className="mt-4 text-[24px] font-semibold tracking-tight">{symbol}</h1>
        <div className="mt-4">
          <Notice>
            Not researched yet.{" "}
            <Link href={`/research?s=${symbol}`} className="font-semibold text-accent">Run research on {symbol} now</Link>
          </Notice>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="pt-6"><Back /></div>
      <div className="mt-3 flex items-baseline gap-2">
        <h1 className="text-[24px] font-semibold tracking-tight">{c.symbol}</h1>
        <span className="text-[12px] text-ink-3">{c.view}</span>
      </div>
      <div className="text-[13.5px] text-ink-2">{c.company}</div>
      <div className="num mt-1 text-[12px] text-ink-3">
        Built {asOfLabel(c.as_of)} from annual reports and earnings-call transcripts only ·{" "}
        <ExtLink href={c.screener_url}>screener.in</ExtLink>
      </div>

      <nav className="no-scrollbar sticky top-0 z-30 -mx-4 mt-3 flex gap-1 overflow-x-auto border-b border-line bg-bg/95 px-4 py-2 backdrop-blur">
        {NAV.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="shrink-0 rounded-md px-2.5 py-1 text-[12.5px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">
            {label}
          </a>
        ))}
      </nav>

      <SectionTitle id="promises" aside="what management said would happen, against what did">Promised vs delivered</SectionTitle>
      <Scoreboard c={c} />

      <SectionTitle id="guidance" aside="open targets, with how the year is going so far">Guidance</SectionTitle>
      <Guidance c={c} onQuote={setQuote} />

      <SectionTitle id="snapshot">Financial snapshot</SectionTitle>
      <Snapshot c={c} />

      <SectionTitle id="trajectory" aside="what's growing, what's compressing">Trajectory</SectionTitle>
      <Trajectory c={c} />

      <SectionTitle id="balance" aside="debt, leverage, cash tied up in operations">Balance sheet</SectionTitle>
      <BalanceSheet c={c} />

      <SectionTitle id="cash" aside="do profits turn into cash?">Cash quality</SectionTitle>
      <CashQuality c={c} />

      <SectionTitle id="business" aside="in management's words">Business snapshot</SectionTitle>
      <Business c={c} onQuote={setQuote} />

      <SectionTitle id="bullbear">Bull vs bear</SectionTitle>
      <BullBear c={c} />

      <SectionTitle id="sources">Sources</SectionTitle>
      <Sources c={c} />

      <QuoteSheet q={quote} onClose={() => setQuote(null)} />
    </div>
  );
}

function Back() {
  return (
    <button onClick={() => history.length > 1 ? history.back() : (location.href = "/")} className="-ml-1 inline-flex items-center gap-0.5 text-[13px] text-ink-2 hover:text-ink">
      <Icon name="back" className="size-4" /> Back
    </button>
  );
}

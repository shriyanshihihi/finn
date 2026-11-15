"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/components/Providers";
import { Chip, Icon, Notice, SectionTitle } from "@/components/ui";
import { API_URL, getJSON } from "@/lib/data";

type Step = { msg: string; done: boolean };

export default function Research() {
  const router = useRouter();
  const { config, holdings } = useStore();
  const [q, setQ] = useState("");
  const [symbols, setSymbols] = useState<{ s: string; n: string }[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [secs, setSecs] = useState(0);
  const es = useRef<EventSource | null>(null);

  useEffect(() => {
    getJSON<{ s: string; n: string }[]>("/data/nse_symbols.json").then(setSymbols).catch(() => setSymbols([]));
    const s = new URLSearchParams(window.location.search).get("s");
    if (s) run(s);
    return () => es.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setSecs((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  const ready = useMemo(() => {
    const r = (config?.research || []).map((x) => ({ s: x.symbol, n: x.name }));
    const h = holdings.filter((x) => x.has_research && !r.some((y) => y.s === x.symbol)).map((x) => ({ s: x.symbol, n: x.name }));
    return [...r, ...h];
  }, [config, holdings]);

  const matches = useMemo(() => {
    const t = q.trim().toUpperCase();
    if (!t) return [];
    const starts = symbols.filter((x) => x.s.startsWith(t));
    const contains = symbols.filter((x) => !x.s.startsWith(t) && x.n.toUpperCase().includes(t));
    return [...starts, ...contains].slice(0, 7);
  }, [q, symbols]);

  async function run(raw: string) {
    const sym = raw.trim().toUpperCase();
    if (!sym) return;
    setErr(null);
    setSteps([]);
    setSecs(0);
    try {
      await getJSON(`/data/companies/${sym}.json`);
      router.push(`/c/${sym}`);
      return;
    } catch {
      /* not precomputed: go live */
    }
    if (!API_URL) {
      setErr("Live research isn't switched on in this deployment. The companies below are ready to open.");
      return;
    }
    setRunning(sym);
    setSteps([{ msg: "Connecting to the research server", done: false }]);
    let heard = false;
    let failures = 0;
    es.current?.close();
    const src = new EventSource(`${API_URL}/research/${encodeURIComponent(sym)}/stream`);
    es.current = src;
    const push = (msg: string) => setSteps((s) => [...s.map((x) => ({ ...x, done: true })), { msg, done: false }]);
    src.addEventListener("progress", (e) => {
      heard = true;
      push(JSON.parse((e as MessageEvent).data).msg);
    });
    src.addEventListener("done", () => {
      src.close();
      setSteps((s) => s.map((x) => ({ ...x, done: true })));
      router.push(`/c/${sym}`);
    });
    src.addEventListener("error", (e) => {
      const data = (e as MessageEvent).data;
      if (data) {
        src.close();
        setRunning(null);
        setErr(JSON.parse(data).msg);
        return;
      }
      failures += 1;
      if (!heard && failures === 1) push("Waking up the research server (free tier sleeps when idle)");
      if (failures > 8) {
        src.close();
        setRunning(null);
        setErr("The research server didn't answer. Try again in a minute, or open a ready company.");
      }
    });
  }

  return (
    <div>
      <h1 className="pt-8 text-[24px] font-semibold tracking-tight">Research any company</h1>
      <p className="mt-1 text-[13.5px] text-ink-2">Built only from annual reports and earnings-call transcripts. No news, no broker notes.</p>

      <form
        className="relative mt-5"
        onSubmit={(e) => {
          e.preventDefault();
          run(matches[0]?.s && q.trim().toUpperCase() !== matches[0].s && !symbols.some((x) => x.s === q.trim().toUpperCase()) ? matches[0].s : q);
        }}
      >
        <div className="flex h-12 items-center gap-2 rounded-xl border border-line-2 bg-surface px-3.5 focus-within:border-ink-3">
          <Icon name="research" className="size-5 text-ink-3" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="NSE symbol or company name"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            disabled={!!running}
            className="h-full flex-1 bg-transparent text-[15px] outline-none placeholder:text-ink-3"
          />
          {q && !running && <button type="submit" className="text-[13px] font-semibold text-accent">Go</button>}
        </div>
        {matches.length > 0 && !running && (
          <div className="absolute inset-x-0 top-[52px] z-20 overflow-hidden rounded-xl border border-line-2 bg-surface shadow-xl">
            {matches.map((m) => (
              <button key={m.s} type="button" onClick={() => { setQ(m.s); run(m.s); }} className="flex w-full items-baseline gap-3 px-3.5 py-2.5 text-left hover:bg-surface-2">
                <span className="w-24 shrink-0 text-[13.5px] font-semibold">{m.s}</span>
                <span className="truncate text-[12.5px] text-ink-2">{m.n}</span>
              </button>
            ))}
          </div>
        )}
      </form>

      {running && (
        <div className="mt-5 rounded-xl border border-line bg-surface p-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[14px] font-semibold">Researching {running}</span>
            <span className="num text-[12px] text-ink-3">{secs}s</span>
          </div>
          <ol className="mt-3 space-y-2">
            {steps.map((s, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[13px]">
                {s.done ? (
                  <Icon name="check" className="mt-0.5 size-4 shrink-0 text-up" />
                ) : (
                  <span className="pulse mt-[5px] size-2 shrink-0 rounded-full bg-accent" />
                )}
                <span className={s.done ? "text-ink-2" : "text-ink"}>{s.msg}</span>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[11.5px] text-ink-3">A new company takes 1–2 minutes the first time. After that it&apos;s cached and opens instantly.</p>
        </div>
      )}

      {err && <div className="mt-5"><Notice>{err}</Notice></div>}

      <SectionTitle aside="already built, open instantly">Ready</SectionTitle>
      <div className="flex flex-wrap gap-2">
        {ready.map((r) => (
          <Chip key={r.s} onClick={() => router.push(`/c/${r.s}`)}>{r.s}</Chip>
        ))}
      </div>

      <SectionTitle>How it reads a company</SectionTitle>
      <ol className="space-y-2 text-[13px] leading-relaxed text-ink-2">
        <li><b className="text-ink">1.</b> Pulls the last 4 earnings-call transcripts and 6 years of reported numbers.</li>
        <li><b className="text-ink">2.</b> Keeps only what management said about the future. Analysts&apos; questions are dropped.</li>
        <li><b className="text-ink">3.</b> A cheap model lists every dated promise with its exact quote. Code checks the quote is really on that page.</li>
        <li><b className="text-ink">4.</b> Code settles what numbers can settle. The stronger model only judges what&apos;s left, from a small table.</li>
      </ol>
    </div>
  );
}

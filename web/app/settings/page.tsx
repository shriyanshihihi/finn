"use client";

import { useState } from "react";
import { useStore } from "@/components/Providers";
import { Card, Chip, Icon, Notice, SectionTitle, Skeleton } from "@/components/ui";
import { METRIC_LABEL, type Settings } from "@/lib/engine";
import { CATEGORY_LABEL, asOfLabel } from "@/lib/format";
import type { Category, Pillar } from "@/lib/types";

function Stepper({ value, step, min, unit, onChange }: { value: number; step: number; min: number; unit: string; onChange: (v: number) => void }) {
  const set = (v: number) => onChange(Math.max(min, Math.round(v * 100) / 100));
  return (
    <div className="flex items-center gap-1">
      <button onClick={() => set(value - step)} className="size-8 rounded-lg border border-line-2 text-[16px] text-ink-2" aria-label="less">−</button>
      <span className="num w-14 text-center text-[14px] font-semibold">{value}{unit}</span>
      <button onClick={() => set(value + step)} className="size-8 rounded-lg border border-line-2 text-[16px] text-ink-2" aria-label="more">+</button>
    </div>
  );
}

export default function SettingsPage() {
  const { ready, meta, config, settings, update, reset } = useStore();
  if (!ready) return <Skeleton />;
  if (!meta || !config || !settings) return <div className="pt-10"><Notice>Couldn&apos;t load settings.</Notice></div>;

  const toggle = (c: Category) =>
    update({ watched: settings.watched.includes(c) ? settings.watched.filter((x) => x !== c) : [...settings.watched, c] });

  return (
    <div>
      <h1 className="pt-8 text-[24px] font-semibold tracking-tight">Settings</h1>
      <p className="mt-1 text-[13.5px] text-ink-2">You decide what counts as unusual. Changes apply instantly and stay on this device.</p>

      <SectionTitle aside="based on end-of-day data">Alerts</SectionTitle>
      <Card className="divide-y divide-line px-4">
        <div className="flex items-center justify-between py-3">
          <div>
            <div className="text-[14px] font-medium">Volume spike</div>
            <div className="text-[12px] text-ink-3">times the 20-session average</div>
          </div>
          <Stepper value={settings.volume_multiple} step={0.25} min={1} unit="×" onChange={(v) => update({ volume_multiple: v })} />
        </div>
        <div className="flex items-center justify-between py-3">
          <div>
            <div className="text-[14px] font-medium">Price move</div>
            <div className="text-[12px] text-ink-3">up or down in one day</div>
          </div>
          <Stepper value={settings.move_pct} step={0.5} min={0.5} unit="%" onChange={(v) => update({ move_pct: v })} />
        </div>
        <Overrides settings={settings} symbols={config.holdings.map((h) => h.symbol)} update={update} />
      </Card>

      <SectionTitle aside="these jump to the top when material">Categories I watch</SectionTitle>
      <div className="flex flex-wrap gap-2">
        {config.categories.map((c) => (
          <Chip key={c} active={settings.watched.includes(c)} onClick={() => toggle(c)}>{CATEGORY_LABEL[c]}</Chip>
        ))}
      </div>

      <SectionTitle id="pillars" aside="why I own each stock, in a form code can check">Pillars</SectionTitle>
      <PillarEditor settings={settings} symbols={config.holdings.map((h) => h.symbol)} categories={config.categories} update={update} />

      <SectionTitle>Appearance</SectionTitle>
      <div className="flex gap-2">
        {(["system", "dark", "light"] as const).map((t) => (
          <Chip key={t} active={settings.theme === t} onClick={() => update({ theme: t })}>{t[0].toUpperCase() + t.slice(1)}</Chip>
        ))}
      </div>

      <SectionTitle>This snapshot</SectionTitle>
      <Card className="num space-y-1 px-4 py-3 text-[12.5px] text-ink-2">
        <div>Data as of {asOfLabel(meta.as_of)}{meta.sample ? " (sample data)" : ""}</div>
        <div>Cheap model: {meta.models.cheap} · strong model: {meta.models.strong}</div>
        <div>{meta.cost.total.calls} model calls, {meta.cost.total.cache_hits} from cache, about ₹{meta.cost.total.inr.toFixed(2)} at paid rates</div>
        {meta.failed_prices.length > 0 && <div>No price data for: {meta.failed_prices.join(", ")}</div>}
      </Card>
      <button onClick={reset} className="mt-4 text-[13px] font-semibold text-down">Reset everything to defaults</button>
    </div>
  );
}

function Overrides({ settings, symbols, update }: { settings: Settings; symbols: string[]; update: (p: Partial<Settings>) => void }) {
  const [sym, setSym] = useState("");
  const entries = Object.entries(settings.overrides);
  const set = (s: string, v: { volume_multiple?: number; move_pct?: number } | null) => {
    const next = { ...settings.overrides };
    if (v) next[s] = v;
    else delete next[s];
    update({ overrides: next });
  };
  return (
    <div className="py-3">
      <div className="text-[14px] font-medium">Per-stock price move</div>
      <div className="text-[12px] text-ink-3">wider bands for volatile names, so alerts keep meaning something</div>
      <div className="mt-2 space-y-2">
        {entries.map(([s, v]) => (
          <div key={s} className="flex items-center justify-between">
            <span className="text-[13.5px] font-semibold">{s}</span>
            <div className="flex items-center gap-2">
              <Stepper value={v.move_pct ?? settings.move_pct} step={0.5} min={0.5} unit="%" onChange={(x) => set(s, { ...v, move_pct: x })} />
              <button onClick={() => set(s, null)} className="p-1 text-ink-3 hover:text-down" aria-label={`Remove ${s}`}><Icon name="close" className="size-4" /></button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <select value={sym} onChange={(e) => setSym(e.target.value)} className="h-9 flex-1 rounded-lg border border-line-2 bg-surface px-2 text-[13px]">
          <option value="">Add a stock…</option>
          {symbols.filter((s) => !settings.overrides[s]).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button disabled={!sym} onClick={() => { set(sym, { move_pct: settings.move_pct + 3 }); setSym(""); }} className="h-9 rounded-lg border border-line-2 px-3 text-[13px] font-medium disabled:opacity-40">Add</button>
      </div>
    </div>
  );
}

const METRICS = ["revenue_yoy", "pat_yoy", "ebitda_margin", "pat_margin", "cfo_to_pat"] as const;

function PillarEditor({ settings, symbols, categories, update }: { settings: Settings; symbols: string[]; categories: Category[]; update: (p: Partial<Settings>) => void }) {
  const [form, setForm] = useState<{ symbol: string; label: string; type: "metric" | "event"; metric: (typeof METRICS)[number]; op: ">=" | "<="; value: string; category: Category }>({
    symbol: symbols[0] || "", label: "", type: "metric", metric: "revenue_yoy", op: ">=", value: "15", category: "pledging",
  });
  const withPillars = symbols.filter((s) => (settings.pillars[s] || []).length);
  const remove = (s: string, id: string) => update({ pillars: { ...settings.pillars, [s]: (settings.pillars[s] || []).filter((p) => p.id !== id) } });
  const add = () => {
    if (!form.symbol || !form.label.trim()) return;
    const p: Pillar = form.type === "metric"
      ? { id: `u-${Date.now()}`, label: form.label.trim(), type: "metric", metric: form.metric, op: form.op, value: Number(form.value) }
      : { id: `u-${Date.now()}`, label: form.label.trim(), type: "event", category: form.category };
    update({ pillars: { ...settings.pillars, [form.symbol]: [...(settings.pillars[form.symbol] || []), p] } });
    setForm({ ...form, label: "" });
  };
  const input = "h-9 rounded-lg border border-line-2 bg-surface px-2 text-[13px]";
  return (
    <div className="space-y-2.5">
      {withPillars.map((s) => (
        <Card key={s} className="px-4 py-2.5">
          <div className="text-[13.5px] font-semibold">{s}</div>
          {(settings.pillars[s] || []).map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-2 py-1">
              <div className="min-w-0 text-[13px]">
                <div className="truncate">{p.label}</div>
                <div className="num text-[11.5px] text-ink-3">
                  {p.type === "metric" ? `${METRIC_LABEL[p.metric!]} ${p.op} ${p.value}${p.metric === "cfo_to_pat" ? "×" : "%"}` : `any ${CATEGORY_LABEL[p.category!].toLowerCase()} filing puts it at risk`}
                </div>
              </div>
              <button onClick={() => remove(s, p.id)} className="p-1 text-ink-3 hover:text-down" aria-label="Remove pillar"><Icon name="close" className="size-4" /></button>
            </div>
          ))}
        </Card>
      ))}
      <Card className="space-y-2 p-4">
        <div className="text-[13px] font-semibold">Add a pillar</div>
        <div className="flex gap-2">
          <select className={`${input} w-32`} value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
            {symbols.map((s) => <option key={s}>{s}</option>)}
          </select>
          <input className={`${input} flex-1`} placeholder="Why I own it, in a few words" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        </div>
        <div className="flex gap-2">
          <Chip active={form.type === "metric"} onClick={() => setForm({ ...form, type: "metric" })}>A number</Chip>
          <Chip active={form.type === "event"} onClick={() => setForm({ ...form, type: "event" })}>An event</Chip>
        </div>
        {form.type === "metric" ? (
          <div className="flex gap-2">
            <select className={`${input} flex-1`} value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value as (typeof METRICS)[number] })}>
              {METRICS.map((m) => <option key={m} value={m}>{METRIC_LABEL[m]}</option>)}
            </select>
            <select className={`${input} w-14`} value={form.op} onChange={(e) => setForm({ ...form, op: e.target.value as ">=" | "<=" })}>
              <option>{">="}</option>
              <option>{"<="}</option>
            </select>
            <input className={`${input} num w-16`} inputMode="decimal" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
          </div>
        ) : (
          <select className={`${input} w-full`} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as Category })}>
            {categories.map((c) => <option key={c} value={c}>Any {CATEGORY_LABEL[c].toLowerCase()} filing</option>)}
          </select>
        )}
        <button onClick={add} disabled={!form.label.trim()} className="h-9 w-full rounded-lg bg-ink text-[13px] font-semibold text-bg disabled:opacity-40">Add pillar</button>
      </Card>
    </div>
  );
}

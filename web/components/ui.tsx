"use client";

import { useEffect } from "react";
import { STATUS_STYLE } from "@/lib/format";

export function Icon({ name, className = "size-5" }: { name: string; className?: string }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const paths: Record<string, React.ReactNode> = {
    today: <><path d="M4 6h16M4 12h10M4 18h6" {...p} /></>,
    holdings: <><rect x="4" y="4" width="7" height="7" rx="1.5" {...p} /><rect x="13" y="4" width="7" height="7" rx="1.5" {...p} /><rect x="4" y="13" width="7" height="7" rx="1.5" {...p} /><rect x="13" y="13" width="7" height="7" rx="1.5" {...p} /></>,
    research: <><circle cx="11" cy="11" r="6" {...p} /><path d="m20 20-4.5-4.5" {...p} /></>,
    settings: <><path d="M4 7h10M18 7h2M4 17h4M12 17h8" {...p} /><circle cx="16" cy="7" r="2" {...p} /><circle cx="10" cy="17" r="2" {...p} /></>,
    ext: <><path d="M14 5h5v5M19 5l-8 8M17 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4" {...p} /></>,
    back: <><path d="M15 5l-7 7 7 7" {...p} /></>,
    chevron: <><path d="m9 6 6 6-6 6" {...p} /></>,
    down: <><path d="m6 9 6 6 6-6" {...p} /></>,
    close: <><path d="M6 6l12 12M18 6 6 18" {...p} /></>,
    quote: <><path d="M7 7h4v4c0 3-2 5-4 6M14 7h4v4c0 3-2 5-4 6" {...p} /></>,
    plus: <><path d="M12 5v14M5 12h14" {...p} /></>,
    check: <><path d="m5 12 5 5 9-10" {...p} /></>,
  };
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      {paths[name]}
    </svg>
  );
}

export function Chip({ active, onClick, children, className = "" }: { active?: boolean; onClick?: () => void; children: React.ReactNode; className?: string }) {
  return (
    <button
      onClick={onClick}
      className={`h-8 shrink-0 rounded-full border px-3 text-[13px] font-medium transition-colors ${
        active ? "border-ink bg-ink text-bg" : "border-line-2 text-ink-2 hover:text-ink"
      } ${className}`}
    >
      {children}
    </button>
  );
}

export function Status({ status }: { status: string }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.pending;
  return <span className={`inline-flex h-5 items-center rounded px-1.5 text-[11px] font-semibold uppercase tracking-wide ${s.cls}`}>{s.label}</span>;
}

export function Tag({ children, tone = "quiet" }: { children: React.ReactNode; tone?: "quiet" | "accent" | "down" | "up" }) {
  const cls = {
    quiet: "text-ink-2 bg-surface-2",
    accent: "text-accent bg-accent-soft",
    down: "text-down bg-down-soft",
    up: "text-up bg-up-soft",
  }[tone];
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11.5px] font-medium ${cls}`}>{children}</span>;
}

export function SectionTitle({ children, aside, id }: { children: React.ReactNode; aside?: React.ReactNode; id?: string }) {
  return (
    <div id={id} className="scroll-mt-16 pb-2.5 pt-7">
      <h2 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">{children}</h2>
      {aside && <div className="mt-0.5 text-[12px] text-ink-3">{aside}</div>}
    </div>
  );
}

export function Card({ children, className = "", accent = false }: { children: React.ReactNode; className?: string; accent?: boolean }) {
  return (
    <div className={`rounded-xl border bg-surface ${accent ? "border-accent/50" : "border-line"} ${className}`}>{children}</div>
  );
}

export function Spark({ values, className = "h-7 w-20", tone }: { values: (number | null)[]; className?: string; tone?: "up" | "down" }) {
  const v = values.filter((x): x is number => x !== null);
  if (v.length < 2) return <div className={className} />;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * 100},${30 - ((x - min) / span) * 28 - 1}`).join(" ");
  const t = tone ?? (v[v.length - 1] >= v[0] ? "up" : "down");
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={className} aria-hidden>
      <polyline points={pts} fill="none" stroke={`var(--${t})`} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", k);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", k);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center" role="dialog" aria-modal aria-label={title}>
      <button className="absolute inset-0 bg-black/55" onClick={onClose} aria-label="Close" />
      <div className="sheet-in relative max-h-[82dvh] w-full max-w-[480px] overflow-y-auto rounded-t-2xl border-t border-line bg-surface px-5 pb-[calc(24px+env(safe-area-inset-bottom))] pt-3">
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-line-2" />
        <div className="mb-3 flex items-start justify-between gap-4">
          <h3 className="text-[15px] font-semibold leading-snug">{title}</h3>
          <button onClick={onClose} className="-mr-1 rounded p-1 text-ink-3 hover:text-ink" aria-label="Close">
            <Icon name="close" className="size-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Cite({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex h-5 items-center gap-1 rounded border border-line-2 px-1.5 text-[11px] font-medium text-ink-2 hover:border-ink-3 hover:text-ink"
    >
      <Icon name="quote" className="size-3" />
      {label}
    </button>
  );
}

export function ExtLink({ href, children, className = "" }: { href?: string | null; children: React.ReactNode; className?: string }) {
  if (!href) return <span className={className}>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`inline-flex items-center gap-1 text-ink-2 underline decoration-line-2 underline-offset-2 hover:text-ink ${className}`}>
      {children}
      <Icon name="ext" className="size-3.5" />
    </a>
  );
}

export function Skeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-3 py-6">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-xl bg-surface" style={{ opacity: 1 - i * 0.18 }} />
      ))}
    </div>
  );
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-dashed border-line-2 px-4 py-5 text-[13.5px] text-ink-2">{children}</div>;
}

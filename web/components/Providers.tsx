"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getJSON } from "@/lib/data";
import { defaultSettings, type Settings } from "@/lib/engine";
import type { Config, Filing, Holding, Meta, PriceStock } from "@/lib/types";

interface Store {
  ready: boolean;
  error: string | null;
  meta: Meta | null;
  config: Config | null;
  filings: Filing[];
  prices: Record<string, PriceStock>;
  holdings: Holding[];
  settings: Settings | null;
  update: (patch: Partial<Settings>) => void;
  reset: () => void;
}

const Ctx = createContext<Store | null>(null);
const KEY = "finn.settings.v1";

function readSaved(): Partial<Settings> {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}");
  } catch {
    return {};
  }
}

function save(s: Settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* private mode: settings live for this visit only */
  }
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Omit<Store, "update" | "reset">>({
    ready: false, error: null, meta: null, config: null, filings: [], prices: {}, holdings: [], settings: null,
  });

  useEffect(() => {
    Promise.all([
      getJSON<Meta>("/data/meta.json"),
      getJSON<Config>("/data/config.json"),
      getJSON<{ items: Filing[] }>("/data/digest.json"),
      getJSON<{ stocks: Record<string, PriceStock> }>("/data/prices.json"),
      getJSON<{ holdings: Holding[] }>("/data/holdings.json"),
    ])
      .then(([meta, config, digest, prices, holdings]) => {
        const settings = { ...defaultSettings(config), ...readSaved() };
        setState({ ready: true, error: null, meta, config, filings: digest.items, prices: prices.stocks, holdings: holdings.holdings, settings });
      })
      .catch((e) => setState((s) => ({ ...s, ready: true, error: `Couldn't load the snapshot (${e.message}). Run the pipeline first.` })));
  }, []);

  // theme
  const theme = state.settings?.theme;
  useEffect(() => {
    if (!theme) return;
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  const update = useCallback((patch: Partial<Settings>) => {
    setState((s) => {
      if (!s.settings) return s;
      const next = { ...s.settings, ...patch };
      save(next);
      return { ...s, settings: next };
    });
  }, []);

  const reset = useCallback(() => {
    setState((s) => {
      if (!s.config) return s;
      const next = { ...defaultSettings(s.config), onboarded: true, theme: s.settings?.theme ?? "system" };
      save(next);
      return { ...s, settings: next };
    });
  }, []);

  const value = useMemo(() => ({ ...state, update, reset }), [state, update, reset]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside Providers");
  return s;
}

"use client";

import { useEffect, useState } from "react";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

const cache = new Map<string, Promise<unknown>>();

export function getJSON<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(path, { cache: "no-store" }).then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      }),
    );
    // let a failed request be retried later
    cache.get(path)!.catch(() => cache.delete(path));
  }
  return cache.get(path) as Promise<T>;
}

export function useJSON<T>(path: string | null): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: !!path,
  });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    getJSON<T>(path)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: String(e.message || e), loading: false }));
    return () => {
      alive = false;
    };
  }, [path]);
  return state;
}

/** Company research: bundled file first, then the live API. */
export async function getCompany<T>(symbol: string): Promise<T | null> {
  try {
    return await getJSON<T>(`/data/companies/${symbol}.json`);
  } catch {
    /* not precomputed */
  }
  if (!API_URL) return null;
  try {
    const r = await fetch(`${API_URL}/company/${symbol}`);
    if (r.ok) return (await r.json()) as T;
  } catch {
    /* api asleep or down */
  }
  return null;
}

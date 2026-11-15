"""End-of-day prices and volumes from Yahoo Finance.

Writes data/prices.json with raw daily metrics for the last 30 sessions of every
holding. Alerts are NOT decided here: the app recomputes them from these numbers
whenever the user changes a threshold. We only mark breaches at the default
thresholds so the snapshot has a sensible default view.
"""
from __future__ import annotations

import math

import pandas as pd
import yfinance as yf

from .common import DATA, iso, log, now_ist, portfolio, write_json

KEEP = 30
AVG_WINDOW = 20


def _history(symbol: str) -> tuple[pd.DataFrame, str]:
    for suffix in (".NS", ".BO"):
        try:
            df = yf.Ticker(symbol + suffix).history(period="9mo", interval="1d", auto_adjust=False)
        except Exception as e:  # yfinance raises all sorts of things
            log("prices", f"{symbol}{suffix}: {e}")
            df = pd.DataFrame()
        if not df.empty and "Close" in df:
            return df, suffix
    return pd.DataFrame(), ""


def metrics_from_frame(df: pd.DataFrame) -> list[dict]:
    """Per session: close, % change, volume, 20-session average volume (excluding that day), multiple."""
    df = df[["Close", "Volume"]].dropna().copy()
    df["change_pct"] = df["Close"].pct_change() * 100
    df["avg_vol_20"] = df["Volume"].shift(1).rolling(AVG_WINDOW, min_periods=10).mean()
    df["vol_multiple"] = df["Volume"] / df["avg_vol_20"]
    out = []
    for ts, r in df.tail(KEEP).iterrows():
        def num(x, nd=2):
            return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)
        out.append({
            "date": pd.Timestamp(ts).strftime("%Y-%m-%d"),
            "close": num(r["Close"]),
            "change_pct": num(r["change_pct"]),
            "volume": int(r["Volume"]),
            "avg_vol_20": num(r["avg_vol_20"], 0),
            "vol_multiple": num(r["vol_multiple"]),
        })
    return out


def breaches(series: list[dict], volume_multiple: float, move_pct: float) -> list[dict]:
    hits = []
    for d in series:
        why = []
        if d["vol_multiple"] is not None and d["vol_multiple"] >= volume_multiple:
            why.append("volume")
        if d["change_pct"] is not None and abs(d["change_pct"]) >= move_pct:
            why.append("move")
        if why:
            hits.append({"date": d["date"], "why": why, "change_pct": d["change_pct"], "vol_multiple": d["vol_multiple"]})
    return hits


def run() -> dict:
    cfg = portfolio()
    alerts = cfg["alerts"]
    out = {"as_of": iso(now_ist()), "stocks": {}, "failed": []}
    for h in cfg["holdings"]:
        sym = h["symbol"]
        df, suffix = _history(sym)
        if df.empty:
            out["failed"].append(sym)
            log("prices", f"{sym}: no data, skipped")
            continue
        series = metrics_from_frame(df)
        ov = alerts.get("overrides", {}).get(sym, {})
        vm = ov.get("volume_multiple", alerts["volume_multiple"])
        mp = ov.get("move_pct", alerts["move_pct"])
        out["stocks"][sym] = {
            "symbol": sym,
            "yahoo": sym + suffix,
            "series": series,
            "last": series[-1] if series else None,
            "default_breaches": breaches(series, vm, mp),
        }
    write_json(DATA / "prices.json", out)

    print(f"\n{'symbol':<12}{'close':>10}{'chg %':>8}{'vol x':>7}  breach")
    for sym, s in out["stocks"].items():
        last = s["last"] or {}
        hit = any(b["date"] == last.get("date") for b in s["default_breaches"])
        print(f"{sym:<12}{last.get('close') or 0:>10.2f}{last.get('change_pct') or 0:>8.2f}"
              f"{last.get('vol_multiple') or 0:>7.2f}  {'YES' if hit else ''}")
    if out["failed"]:
        print("failed:", ", ".join(out["failed"]))
    return out


if __name__ == "__main__":
    run()

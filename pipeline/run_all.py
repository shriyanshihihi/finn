"""Run the whole pipeline, in order, and print a short report.

    python -m pipeline.run_all            # everything
    python -m pipeline.run_all --fast     # reuse cached company research, refresh prices + filings only

Re-runs are cheap: every model answer is cached, so only new filings cost anything.
"""
from __future__ import annotations

import argparse
import os
import csv
import io
import time

from . import announcements, build_digest, classify, fundamentals, llm, prices, research
from .common import WEB_DATA, log, portfolio, read_json, session, write_json


def symbols_list(extra: list[str]) -> None:
    """All NSE equity symbols, for the search box. Keeps the old file if NSE blocks us."""
    path = WEB_DATA / "nse_symbols.json"
    try:
        s = session(referer="https://www.nseindia.com/")
        r = s.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", timeout=30)
        r.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(r.text)))
        out = [{"s": x["SYMBOL"].strip(), "n": x["NAME OF COMPANY"].strip()} for x in rows if x.get("SYMBOL")]
        write_json(path, out)
        log("symbols", f"{len(out)} NSE symbols")
    except Exception as e:
        old = read_json(path, [])
        have = {x["s"] for x in old}
        old += [{"s": s, "n": s} for s in extra if s not in have]
        write_json(path, old)
        log("symbols", f"NSE list not reachable ({str(e)[:60]}), kept {len(old)} symbols")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="don't rebuild company research")
    args = ap.parse_args()
    t0 = time.time()
    cfg = portfolio()
    holdings = [h["symbol"] for h in cfg["holdings"]]
    research_set = cfg.get("research", [])
    everyone = list(dict.fromkeys(holdings + research_set))

    if not llm.available("cheap"):
        print("\n!! No GEMINI_API_KEY / GROQ_API_KEY in .env. Rules, prices and numbers will work;"
              " summaries, promise ledgers and bull/bear will be skipped.\n")

    log("step", "1/6 prices")
    prices.run()
    log("step", "2/6 fundamentals from screener.in")
    fund = fundamentals.run(everyone)
    log("step", "3/6 announcements")
    announcements.run(holdings)
    log("step", "4/6 classify")
    classify.run()

    log("step", "5/6 company research + promise ledgers")
    # Research set first, then holdings. Full ledgers until the time budget runs out
    # (free-tier model calls are slow); after that, holdings get numbers-only pages
    # so every stock still has a company page.
    full_for_holdings = cfg.get("ledger_for_holdings", True)
    budget_s = float(os.environ.get("RESEARCH_BUDGET_MIN", "0") or 0) * 60
    t_research = time.time()
    targets = research_set + [s for s in holdings if s not in research_set]
    done, failed = [], []
    for sym in targets:
        if sym in fund["failed"]:
            failed.append(sym)
            continue
        over_budget = budget_s and time.time() - t_research > budget_s
        numbers_only = (sym not in research_set and not full_for_holdings) or bool(over_budget)
        try:
            research.build(sym, progress=lambda m, s=sym: log("research", f"{s}: {m}"), refresh=not args.fast,
                           numbers_only=numbers_only)
            done.append(sym)
        except Exception as e:
            failed.append(sym)
            log("research", f"{sym}: FAILED {str(e)[:120]}")

    log("step", "6/6 digest + export")
    symbols_list(everyone)
    meta = build_digest.run()

    c = meta["cost"]["total"]
    st = meta["classify"]
    print("\n" + "=" * 64)
    print(f"as of        {meta['as_of']}")
    print(f"filings      {st.get('total', 0)} total, {st.get('by_rules', 0)} classified by rules, "
          f"{st.get('by_model', 0)} by model, {st.get('material', 0)} material")
    print(f"research     {len(done)} companies ok" + (f", failed: {', '.join(failed)}" if failed else ""))
    print(f"model use    {c['calls']} calls, {c['cache_hits']} cache hits, ~Rs {c['inr']:.2f} at paid rates")
    print(f"took         {time.time() - t0:.0f}s")
    print("=" * 64)
    print("Next: cd web && npm run dev   (or commit web/public/data and push to deploy)")


if __name__ == "__main__":
    main()

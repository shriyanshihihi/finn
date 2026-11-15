"""Join everything into the snapshot the app reads (web/public/data/).

Facts are decided here. Preferences are NOT: tiers depend on which categories I
watch and on my pillars, and alerts depend on my thresholds. The app applies those
in the browser, so they can be changed in Settings without re-running anything.
"""
from __future__ import annotations

import shutil

from . import llm, results, signals
from .classify import CATEGORIES
from .common import DATA, WEB_DATA, iso, load_yaml, log, now_ist, portfolio, read_json, write_json


def _holding_metrics(sym: str) -> dict:
    f = read_json(DATA / "fundamentals" / f"{sym}.json")
    if not f:
        return {}
    qs = [q for q in f["quarterly"] if q.get("revenue") is not None]
    if not qs:
        return {}
    last = qs[-1]
    ago = next((q for q in qs if q["fy"] == last["fy"] - 1 and q["q"] == last["q"]), None)

    def g(a, b):
        return None if a is None or not b else round((a - b) / abs(b) * 100, 1)

    e = last.get("ebitda")
    m = {
        "quarter": last["quarter"],
        "revenue_yoy": g(last["revenue"], ago and ago["revenue"]),
        "pat_yoy": g(last.get("pat"), ago and ago.get("pat")),
        "ebitda_margin": round(e / last["revenue"] * 100, 1) if e is not None and last["revenue"] else None,
        "pat_margin": round(last["pat"] / last["revenue"] * 100, 1) if last.get("pat") is not None and last["revenue"] else None,
    }
    ann = [a for a in f["annual"] if a.get("cfo") is not None and a.get("pat")]
    if ann:
        m["cfo_to_pat"] = round(ann[-1]["cfo"] / ann[-1]["pat"], 2)
        m["cfo_to_pat_year"] = ann[-1]["label"]
    return m


def run(sample: bool = False) -> dict:
    cfg = portfolio()
    ann = read_json(DATA / "classified.json", {"items": [], "stats": {}})
    prices = read_json(DATA / "prices.json", {"stocks": {}})
    names = {}
    for h in cfg["holdings"] + [{"symbol": s} for s in cfg.get("research", [])]:
        f = read_json(DATA / "fundamentals" / f"{h['symbol']}.json")
        names[h["symbol"]] = (f or {}).get("name", h["symbol"])

    items = []
    for it in ann["items"]:
        it = dict(it)
        it["company"] = names.get(it["symbol"], it.get("company"))
        links = {}
        if it["category"] == "results" and it["material"] and it.get("time"):
            card = results.build_card(it["symbol"], it["time"], it.get("excerpt", ""), it.get("url"))
            it["results_card"] = card
            if card and card.get("settles"):
                links["settles"] = len(card["settles"])
        if it["category"] == "management_change" and it["material"]:
            it["management"] = signals.management_card(it, it["company"])
            orph = sum(len(p.get("orphaned_promises") or []) for p in it["management"]["people"])
            if orph:
                links["orphaned"] = orph
        if it["category"] == "earnings_call" and it["material"]:
            L = read_json(DATA / "promises" / f"{it['symbol']}.json")
            if L:
                links["ledger_updated"] = True
        it["promise_links"] = links
        it.pop("excerpt", None)
        items.append(it)

    holdings = []
    for h in cfg["holdings"]:
        sym = h["symbol"]
        L = read_json(DATA / "promises" / f"{sym}.json")
        f = read_json(DATA / "fundamentals" / f"{sym}.json") or {}
        p = prices["stocks"].get(sym, {})
        holdings.append({
            "symbol": sym, "name": names.get(sym, sym), "sector": h.get("sector", ""),
            "company_type": f.get("company_type", "corporate"),
            "last": p.get("last"), "spark": [d["close"] for d in p.get("series", [])][-20:],
            "metrics": _holding_metrics(sym),
            "credibility": (L or {}).get("credibility"),
            "ledger_counts": (L or {}).get("counts"),
            "has_research": (DATA / "companies" / f"{sym}.json").exists(),
        })

    rules = load_yaml("rules.yaml")
    cost = llm.cost_summary()
    meta = {
        "as_of": iso(now_ist()),
        "sample": sample,
        "lookback_days": cfg.get("lookback_days", 14),
        "classify": ann.get("stats", {}),
        "cost": cost,
        "models": {k: v["model"] for k, v in load_yaml("models.yaml").items() if isinstance(v, dict)},
        "failed_prices": prices.get("failed", []),
    }
    config = {
        "holdings": [{"symbol": h["symbol"], "sector": h.get("sector", ""), "name": names.get(h["symbol"], h["symbol"])}
                     for h in cfg["holdings"]],
        "research": [{"symbol": s, "name": names.get(s, s)} for s in cfg.get("research", [])],
        "alerts": cfg["alerts"], "watched_categories": cfg["watched_categories"],
        "pillars": cfg.get("pillars", {}), "categories": CATEGORIES,
        "default_material": rules["default_material"],
    }

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    write_json(WEB_DATA / "meta.json", meta)
    write_json(WEB_DATA / "config.json", config)
    write_json(WEB_DATA / "prices.json", prices)
    write_json(WEB_DATA / "digest.json", {"as_of": meta["as_of"], "items": items})
    write_json(WEB_DATA / "holdings.json", {"as_of": meta["as_of"], "holdings": holdings})
    comp_dir = WEB_DATA / "companies"
    if comp_dir.exists():
        shutil.rmtree(comp_dir)  # no stale or sample company pages survive a run
    comp_dir.mkdir()
    for p in (DATA / "companies").glob("*.json"):
        shutil.copy(p, comp_dir / p.name)
    log("digest", f"{len(items)} filings, {len(holdings)} holdings, "
        f"{len(list(comp_dir.glob('*.json')))} company pages written to web/public/data")
    return meta

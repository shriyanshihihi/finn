"""Results card: Revenue, EBITDA, PBT, PAT for the quarter, vs last quarter and vs a year ago.

Numbers come from screener.in's quarterly table (built from the filings). If screener
hasn't caught up with a brand-new filing yet, the cheap model reads the results PDF
itself (every Indian results statement shows this quarter, last quarter and the
same quarter last year side by side). When both exist, PAT is cross-checked.

Banks and NBFCs have no EBITDA. For them the card shows revenue, financing profit,
PBT and PAT, and says why.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from . import llm
from .common import DATA, pct_change, qindex, qlabel, quarter_discussed_on_call, read_json


class Col(BaseModel):
    revenue: Optional[float] = None
    other_income: Optional[float] = None
    finance_costs: Optional[float] = None
    depreciation: Optional[float] = None
    pbt: Optional[float] = None
    pat: Optional[float] = None


class FilingNumbers(BaseModel):
    found: bool
    basis: Literal["consolidated", "standalone"] = "consolidated"
    unit: Literal["crore", "lakh", "million", "thousand", "rupees"] = "crore"
    current: Col = Col()
    previous_quarter: Col = Col()
    year_ago: Col = Col()


TO_CRORE = {"crore": 1, "lakh": 0.01, "million": 0.1, "thousand": 0.0001, "rupees": 1e-7}


def quarter_of_filing(when_iso: str) -> tuple[int, int]:
    d = datetime.fromisoformat(when_iso)
    return quarter_discussed_on_call(d.month, d.year)


def _ebitda(c: dict) -> float | None:
    if c.get("pbt") is None:
        return None
    return round(c["pbt"] + (c.get("finance_costs") or 0) + (c.get("depreciation") or 0) - (c.get("other_income") or 0), 2)


def from_filing(excerpt: str, symbol: str) -> dict | None:
    if not excerpt or len(excerpt) < 400:
        return None
    prompt = (
        f"This is the start of a quarterly results filing by {symbol} on an Indian stock exchange.\n"
        "Read the results table. Prefer CONSOLIDATED figures if both are present.\n"
        "For three columns - this quarter, the previous quarter, and the same quarter last year - give:\n"
        "revenue (revenue from operations), other_income, finance_costs, depreciation (incl. amortisation), "
        "pbt (profit before tax), pat (net profit for the period).\n"
        "unit = the unit the table states (crore / lakh / million / thousand / rupees). Numbers as plain numbers.\n"
        "If there is no results table in the text, return {\"found\": false}.\n"
        'Return JSON: {"found", "basis", "unit", "current": {...}, "previous_quarter": {...}, "year_ago": {...}}\n\n'
        + excerpt[:12000]
    )
    try:
        r = llm.cheap(prompt, step="results_pdf", schema=FilingNumbers)
    except (llm.LLMUnavailable, llm.LLMError):
        return None
    if not r["found"]:
        return None
    k = TO_CRORE.get(r["unit"], 1)
    out = {}
    for col in ("current", "previous_quarter", "year_ago"):
        c = {key: (v * k if v is not None else None) for key, v in r[col].items()}
        c["ebitda"] = _ebitda(c)
        out[col] = c
    out["basis"] = r["basis"]
    return out


def _metric(label, key, cur, prev, ago, note=None):
    v = cur.get(key) if cur else None
    return {"key": key, "label": label, "value": v,
            "qoq": pct_change(v, prev.get(key) if prev else None),
            "yoy": pct_change(v, ago.get(key) if ago else None), "note": note}


def _margin(row, key):
    if not row or row.get(key) is None or not row.get("revenue"):
        return None
    return round(row[key] / row["revenue"] * 100, 1)


def _pp(a, b):
    return None if a is None or b is None else round(a - b, 1)


def build_card(symbol: str, filed_at: str, excerpt: str = "", filing_url: str | None = None) -> dict | None:
    f = read_json(DATA / "fundamentals" / f"{symbol}.json")
    fy, q = quarter_of_filing(filed_at)
    lender = bool(f and f.get("company_type") == "lender")
    cur = prev = ago = None
    source = None
    if f:
        rows = {qindex(r["fy"], r["q"]): r for r in f["quarterly"]}
        cur = rows.get(qindex(fy, q))
        prev = rows.get(qindex(fy, q) - 1)
        ago = rows.get(qindex(fy - 1, q))
        if cur and cur.get("revenue") is not None:
            source = "screener"
    filing = None if lender else from_filing(excerpt, symbol)
    check = None
    if source is None and filing:
        cur, prev, ago = filing["current"], filing["previous_quarter"], filing["year_ago"]
        source = "filing"
    elif source and filing and filing["current"].get("pat") and cur.get("pat"):
        diff = abs(filing["current"]["pat"] - cur["pat"]) / abs(cur["pat"]) * 100 if cur["pat"] else 0
        check = {"pat_filing": round(filing["current"]["pat"], 1), "pat_screener": cur["pat"],
                 "diff_pct": round(diff, 1), "mismatch": diff > 2}
    if source is None:
        return {"symbol": symbol, "quarter": qlabel(fy, q), "available": False,
                "note": "Numbers for this quarter aren't on screener.in yet and the filing couldn't be read.",
                "filing_url": filing_url}

    if lender:
        metrics = [
            _metric("Revenue", "revenue", cur, prev, ago, "Interest earned + other operating income"),
            _metric("Financing profit", "financing_profit", cur, prev, ago, "Lenders have no EBITDA"),
            _metric("PBT", "pbt", cur, prev, ago),
            _metric("PAT", "pat", cur, prev, ago),
        ]
        margins = []
    else:
        metrics = [
            _metric("Revenue", "revenue", cur, prev, ago),
            _metric("EBITDA", "ebitda", cur, prev, ago, "Operating profit, excl. other income"),
            _metric("PBT", "pbt", cur, prev, ago),
            _metric("PAT", "pat", cur, prev, ago),
        ]
        em = [_margin(x, "ebitda") for x in (cur, prev, ago)]
        pm = [_margin(x, "pat") for x in (cur, prev, ago)]
        margins = [
            {"label": "EBITDA margin", "value": em[0], "qoq_pp": _pp(em[0], em[1]), "yoy_pp": _pp(em[0], em[2])},
            {"label": "PAT margin", "value": pm[0], "qoq_pp": _pp(pm[0], pm[1]), "yoy_pp": _pp(pm[0], pm[2])},
        ]

    # promises that fall due this quarter (or this year, on a Q4 card)
    settled = []
    L = read_json(DATA / "promises" / f"{symbol}.json")
    if L:
        for t in L["threads"]:
            due_q = t.get("deadline_fy") == fy and t.get("deadline_q") == q
            due_y = t.get("deadline_fy") == fy and not t.get("deadline_q") and q == 4
            if due_q or due_y:
                settled.append({"id": t["id"], "metric": t["metric"], "target": t["target_text"],
                                "status": t["display_status"], "actual": t.get("actual_text", ""),
                                "speaker": ", ".join(t["speakers"])})
    return {
        "symbol": symbol, "quarter": qlabel(fy, q), "available": True, "lender": lender,
        "source": source, "basis": (f or {}).get("view") if source == "screener" else (filing or {}).get("basis"),
        "source_url": (f or {}).get("url") if source == "screener" else filing_url,
        "filing_url": filing_url or (cur.get("filing_url") if cur else None),
        "metrics": metrics, "margins": margins, "check": check, "settles": settled,
    }

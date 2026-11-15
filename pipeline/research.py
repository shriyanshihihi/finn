"""On-demand research for any NSE ticker, grounded in primary sources only.

Sections (the brief's menu):
  narrative vs numbers  -> the Promise Ledger (pipeline.promises)
  guidance              -> open promises, with how the year is going so far
  financial snapshot    -> latest quarter, TTM, ROCE, debt/equity          (code, no model)
  trajectory            -> 6-year revenue / EBITDA / PAT and margins       (code, no model)
  balance sheet         -> debt, leverage, working-capital cycle           (code, no model)
  cash quality          -> cash from operations vs profit, every year      (code, no model)
  business snapshot     -> what management says the business is, from the latest call (cheap model)
  bull vs bear          -> both cases + a red-team of my own pillars        (strong model, small input)

Nothing here uses news, broker notes or the model's own memory of the company.

Usage: python -m pipeline.research PGEL
"""
from __future__ import annotations

import re
import sys
from typing import Callable, Optional

from pydantic import BaseModel

from . import fundamentals, llm, promises
from .common import DATA, iso, log, now_ist, portfolio, read_json, write_json

OUT = DATA / "companies"


# ---------------------------------------------------------------- code-only sections

def _r(x, n=1):
    return None if x is None else round(x, n)


def _cagr(a, b, years):
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def _margin(row, key="ebitda"):
    v = row.get(key) if row.get(key) is not None else row.get("financing_profit")
    if v is None or not row.get("revenue"):
        return row.get("opm")
    return round(v / row["revenue"] * 100, 1)


def financial_snapshot(f: dict) -> dict:
    qs = [q for q in f["quarterly"] if q.get("revenue") is not None]
    if not qs:
        return {}
    last = qs[-1]
    ago = next((q for q in qs if q["fy"] == last["fy"] - 1 and q["q"] == last["q"]), None)
    ttm = qs[-4:]
    ann = [a for a in f["annual"] if a.get("revenue") is not None]
    la = ann[-1] if ann else {}
    de = (la.get("borrowings") / la["equity"]) if la.get("borrowings") is not None and la.get("equity") else None
    lender = f["company_type"] == "lender"
    tiles = [
        {"label": f"Revenue {last['quarter']}", "value": last["revenue"], "unit": "cr",
         "delta": _pct(last["revenue"], ago and ago["revenue"]), "delta_label": "YoY"},
        {"label": "Financing profit" if lender else "EBITDA margin", "value": last.get("financing_profit") if lender else _margin(last),
         "unit": "cr" if lender else "%",
         "delta": None if lender else _pp(_margin(last), ago and _margin(ago)), "delta_label": "pp YoY"},
        {"label": f"PAT {last['quarter']}", "value": last.get("pat"), "unit": "cr",
         "delta": _pct(last.get("pat"), ago and ago.get("pat")), "delta_label": "YoY"},
        {"label": "Revenue TTM", "value": sum(q["revenue"] for q in ttm) if len(ttm) == 4 else None, "unit": "cr"},
        {"label": "PAT TTM", "value": sum((q.get("pat") or 0) for q in ttm) if len(ttm) == 4 else None, "unit": "cr"},
        {"label": "ROE" if lender else "ROCE", "value": la.get("roce"), "unit": "%"},
        {"label": "Debt / equity", "value": None if lender else _r(de, 2), "unit": "x",
         "note": "Not meaningful for a lender" if lender else None},
        {"label": "Market cap", "value": f["top_ratios"].get("Market Cap"), "unit": "cr"},
    ]
    return {"quarter": last["quarter"], "tiles": tiles, "source": "screener.in quarterly + annual tables"}


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a - b) / abs(b) * 100, 1)


def _pp(a, b):
    return None if a is None or b is None else round(a - b, 1)


def trajectory(f: dict) -> dict:
    ann = [a for a in f["annual"] if a.get("revenue") is not None][-6:]
    rows = [{"fy": a["label"], "revenue": a["revenue"], "ebitda": a.get("ebitda") if a.get("ebitda") is not None else a.get("financing_profit"),
             "margin": _margin(a), "pat": a.get("pat")} for a in ann]
    lines = []
    if len(ann) >= 4:
        a0, a1 = ann[-4], ann[-1]
        rc, pc = _cagr(a0["revenue"], a1["revenue"], 3), _cagr(a0.get("pat"), a1.get("pat"), 3)
        m0, m1 = _margin(a0), _margin(a1)
        if rc is not None:
            lines.append({"label": "Revenue, 3-yr CAGR", "value": rc, "unit": "%",
                          "tone": "up" if rc >= 10 else "flat" if rc >= 0 else "down"})
        if pc is not None:
            lines.append({"label": "PAT, 3-yr CAGR", "value": pc, "unit": "%",
                          "tone": "up" if pc >= 10 else "flat" if pc >= 0 else "down"})
        if m0 is not None and m1 is not None:
            d = round(m1 - m0, 1)
            lines.append({"label": "Margin change, 3 yrs", "value": d, "unit": "pp",
                          "tone": "up" if d > 0.5 else "down" if d < -0.5 else "flat"})
    quarters = [{"q": q["quarter"], "revenue": q["revenue"], "margin": _margin(q), "pat": q.get("pat")}
                for q in f["quarterly"] if q.get("revenue") is not None][-8:]
    return {"years": rows, "quarters": quarters, "headline": lines, "source": "screener.in annual + quarterly tables"}


def balance_sheet(f: dict) -> dict:
    ann = [a for a in f["annual"] if a.get("borrowings") is not None or a.get("equity") is not None][-5:]
    rows = []
    for a in ann:
        de = a["borrowings"] / a["equity"] if a.get("borrowings") is not None and a.get("equity") else None
        rows.append({"fy": a["label"], "borrowings": a.get("borrowings"), "equity": a.get("equity"),
                     "de": _r(de, 2), "wc_days": a.get("wc_days"), "ccc": a.get("ccc"),
                     "debtor_days": a.get("debtor_days"), "cwip": a.get("cwip")})
    note = None
    if f["company_type"] == "lender":
        note = "For a lender, borrowing is the raw material, so debt/equity and working-capital days don't mean what they do for a manufacturer."
    elif len(rows) >= 2 and rows[-1].get("ccc") is not None and rows[0].get("ccc") is not None:
        d = rows[-1]["ccc"] - rows[0]["ccc"]
        if d > 15:
            note = f"Cash conversion cycle stretched by {d:.0f} days over {len(rows) - 1} years: more cash is tied up in operations."
        elif d < -15:
            note = f"Cash conversion cycle shortened by {abs(d):.0f} days over {len(rows) - 1} years."
    return {"years": rows, "note": note, "source": "screener.in balance sheet + ratios"}


def cash_quality(f: dict) -> dict:
    ann = [a for a in f["annual"] if a.get("cfo") is not None and a.get("pat") is not None][-6:]
    rows = [{"fy": a["label"], "cfo": a["cfo"], "pat": a["pat"],
             "ratio": _r(a["cfo"] / a["pat"], 2) if a["pat"] else None,
             "after_investing": _r(a["cfo"] + (a.get("cfi") or 0), 0)} for a in ann]
    cum_cfo = sum(r["cfo"] for r in rows[-5:])
    cum_pat = sum(r["pat"] for r in rows[-5:])
    ratio = _r(cum_cfo / cum_pat, 2) if cum_pat else None
    if ratio is None:
        verdict = None
    elif ratio >= 0.9:
        verdict = "Profits are turning into cash."
    elif ratio >= 0.6:
        verdict = "Part of the profit is getting stuck in working capital."
    else:
        verdict = "Most of the reported profit is not showing up as cash."
    return {"years": rows, "five_year_ratio": ratio, "verdict": verdict,
            "lender": f["company_type"] == "lender",
            "source": "screener.in cash flow statement"}


def guidance(L: dict) -> list[dict]:
    out = []
    for t in L.get("threads", []):
        if t["display_status"] in ("pending", "revised", "dropped"):
            m = t["mentions"][-1]
            out.append({"id": t["id"], "metric": t["metric"], "target": t["target_text"], "deadline": t["deadline"],
                        "status": t["display_status"], "progress": t.get("progress", ""), "said_by": m["speaker_name"],
                        "said": m["quarter_said"], "quote": m["verbatim_quote"], "page": m["page"],
                        "transcript_url": m["transcript_url"]})
    return sorted(out, key=lambda x: x["deadline"])


# ---------------------------------------------------------------- model sections

class Segment(BaseModel):
    name: str
    detail: str
    page: int


class Business(BaseModel):
    what_they_do: str
    page: int
    segments: list[Segment]
    revenue_mix: Optional[str] = None
    mix_page: Optional[int] = None


def business_snapshot(sym: str, company: str) -> dict | None:
    T = read_json(DATA / "transcripts" / f"{sym}.json")
    if not T or not T["calls"]:
        return None
    call = T["calls"][0]
    words, parts = 0, []
    for t in call["turns"]:
        parts.append(f"[p.{t['page']}] {t['speaker']}: {t['text']}")
        words += len(t["text"].split())
        if words > 2500:
            break
    if not parts:
        return None
    prompt = (
        f"Management's remarks from {company}'s {call['quarter']} earnings call ({call['date_label']}), tagged by page.\n"
        "Using ONLY this text:\n"
        "- what_they_do: the business in at most 2 plain sentences, and the page it comes from\n"
        "- segments: each business segment named, with what was said about it (max 14 words) and its page\n"
        "- revenue_mix: the revenue split by segment or geography IF stated, else null; mix_page\n"
        'Return JSON: {"what_they_do", "page", "segments": [{"name", "detail", "page"}], "revenue_mix", "mix_page"}\n\n'
        + "\n".join(parts)[:20000]
    )
    try:
        b = llm.cheap(prompt, step="business_snapshot", schema=Business)
    except (llm.LLMUnavailable, llm.LLMError):
        return None
    b.update({"source": f"{call['quarter']} earnings call", "transcript_url": call["url"]})
    return b


class Point(BaseModel):
    text: str
    source: str


class PillarCheck(BaseModel):
    pillar_id: str
    bear: str
    would_prove_wrong: str
    source: str
    supported: bool


class BullBear(BaseModel):
    bull: list[Point]
    bear: list[Point]
    pillars: list[PillarCheck]


KEYWORDS = r"margin|growth|demand|competition|pricing|price|working capital|receivable|inventory|debt|capex|capacity|" \
           r"utili[sz]ation|order|guidance|volume|cost|raw material|export|market share|cash"


def _passages(sym: str, pillar_words: list[str], k: int = 20) -> list[str]:
    T = read_json(DATA / "transcripts" / f"{sym}.json")
    if not T:
        return []
    rx = re.compile("|".join([KEYWORDS] + [re.escape(w) for w in pillar_words if len(w) > 3]), re.I)
    scored = []
    for call in T["calls"]:
        for t in call["turns"]:
            for chunk in re.split(r"(?<=[.?!])\s+(?=[A-Z])", t["text"]):
                n = len(rx.findall(chunk))
                if n and len(chunk) > 60:
                    scored.append((n, f"[{call['quarter']} call p.{t['page']}] {t['speaker']}: {chunk[:600]}"))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:k]]


def bull_bear(sym: str, f: dict, L: dict, pillars: list[dict]) -> dict | None:
    words = []
    for p in pillars:
        words += re.findall(r"[a-zA-Z]+", p["label"])
    passages = _passages(sym, words)
    if not passages and not L.get("threads"):
        return None
    ledger = "\n".join(f"- {t['metric']}: target {t['target_text']} by {t['deadline']} -> {t['display_status']} {t.get('actual_text', '')}"
                       for t in L.get("threads", [])[:25])
    pil = "\n".join(f"- {p['id']}: {p['label']} ({p.get('metric', p.get('category'))} {p.get('op', '')} {p.get('value', '')})"
                    for p in pillars) or "(none - this company is not in the portfolio)"
    prompt = (
        f"Company: {f['name']} ({sym}). You are a sceptical analyst at a long-only fund.\n"
        "Use ONLY the material below: reported numbers, management's promise track record, and quotes from "
        "management on earnings calls. No outside knowledge, no news.\n\n"
        f"REPORTED NUMBERS\n{promises._numbers_table(f)}\n\nPROMISE TRACK RECORD\n{ledger or '(none)'}\n\n"
        f"MANAGEMENT PASSAGES\n" + "\n".join(passages) + f"\n\nMY PILLARS (why I own it)\n{pil}\n\n"
        "Write:\n"
        "- bull: 3 points, each max 25 words, each with source like 'Q2 FY27 call p.7' or 'reported numbers'\n"
        "- bear: 3 points, same rules\n"
        "- pillars: for EACH pillar above, the strongest bear argument against it (max 2 lines), what evidence "
        "would prove that bear case wrong (max 1 line), its source, and supported=false if the material "
        "doesn't support any real bear case (then say so in 'bear'). Empty list if no pillars.\n"
        'Return JSON: {"bull": [{"text", "source"}], "bear": [...], "pillars": [{"pillar_id", "bear", "would_prove_wrong", "source", "supported"}]}'
    )
    try:
        return llm.strong(prompt, step="bull_bear", schema=BullBear)
    except (llm.LLMUnavailable, llm.LLMError) as e:
        log("research", f"{sym}: bull/bear skipped ({str(e)[:80]})")
        return None


# ---------------------------------------------------------------- main

def build(sym: str, progress: Callable[[str], None] = lambda m: None, refresh: bool = False) -> dict:
    sym = sym.upper().strip()
    path = OUT / f"{sym}.json"
    if not refresh and path.exists():
        return read_json(path)
    f = fundamentals.get(sym, refresh=refresh)
    progress(f"Found {f['name']}: {len(f['quarterly'])} quarters, {len(f['transcripts'])} transcripts")
    try:
        L = promises.build(sym, progress=progress, refresh=refresh)
    except llm.LLMUnavailable:
        L = {"threads": [], "credibility": {}, "counts": {}, "summary": "", "transcripts": [],
             "note": "Promise ledger needs a model key (GEMINI_API_KEY)."}
    progress("Building snapshot, trajectory, balance sheet and cash quality")
    pillars = portfolio().get("pillars", {}).get(sym, [])
    progress("Reading management's description of the business")
    biz = business_snapshot(sym, f["name"])
    progress("Writing bull and bear cases")
    bb = bull_bear(sym, f, L, pillars)
    out = {
        "symbol": sym, "company": f["name"], "as_of": iso(now_ist()), "view": f["view"],
        "company_type": f["company_type"], "screener_url": f["url"], "about": f.get("about", ""),
        "ledger": L,
        "guidance": guidance(L),
        "financial_snapshot": financial_snapshot(f),
        "trajectory": trajectory(f),
        "balance_sheet": balance_sheet(f),
        "cash_quality": cash_quality(f),
        "business": biz,
        "bull_bear": bb,
        "pillars": pillars,
        "sources": {
            "screener": f["url"],
            "transcripts": [{"label": f"{t['quarter']} call ({t['date_label']})", "url": t["url"]} for t in f["transcripts"][:4]],
            "annual_reports": f["annual_reports"][:3],
        },
    }
    write_json(path, out)
    progress("Done")
    return out


if __name__ == "__main__":
    for s in sys.argv[1:] or ["POLYCAB"]:
        r = build(s, progress=lambda m: log("research", m), refresh=True)
        promises.print_ledger(r["ledger"]) if r["ledger"].get("threads") is not None and r["ledger"].get("company") else None
        print("cash quality:", r["cash_quality"].get("verdict"), r["cash_quality"].get("five_year_ratio"))

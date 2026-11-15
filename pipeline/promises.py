"""The Promise Ledger: what management said would happen vs what happened.

Steps for one company (works for any NSE symbol screener.in covers):
  1. last 4 concall transcripts -> speaker turns (pipeline.transcripts)
  2. keep only MANAGEMENT sentences that talk about the future (cuts most tokens)
  3. cheap model extracts promises, each with an exact quote and page
  4. code checks every quote really is on that page; anything else is dropped
  5. code links the same promise across calls: reaffirmed / revised / quietly dropped
  6. code settles promises it can compute from reported numbers (growth, margin, revenue, PAT)
  7. the strong model only sees a small table, for the promises code can't settle
     and for a short "narrative vs numbers" read

Usage: python -m pipeline.promises POLYCAB
"""
from __future__ import annotations

import re
import sys
from typing import Callable, Literal, Optional

from pydantic import BaseModel
from rapidfuzz import fuzz

from . import fundamentals, llm
from .common import DATA, iso, log, now_ist, qindex, qlabel, read_json, session, write_json
from .transcripts import approx_tokens, forward_looking, load as load_transcript

OUT = DATA / "promises"
TDIR = DATA / "transcripts"
N_CALLS = 4

MetricKey = Literal["revenue_growth", "revenue", "ebitda_margin", "ebitda_growth", "pat_growth", "pat",
                    "capex", "capacity", "volume_growth", "debt", "working_capital", "other"]


class Extracted(BaseModel):
    metric: str
    metric_key: MetricKey
    target_text: str
    target_low: Optional[float] = None
    target_high: Optional[float] = None
    unit: str = ""
    deadline_text: str = ""
    deadline_fy: Optional[int] = None
    deadline_q: Optional[int] = None
    speaker_name: str
    verbatim_quote: str
    page: int


class Extraction(BaseModel):
    items: list[Extracted]


class Verdict(BaseModel):
    id: str
    status: Literal["kept", "missed", "pending", "unverifiable"]
    actual_text: str
    reason: str


class Verdicts(BaseModel):
    verdicts: list[Verdict]
    summary: str


# ---------------------------------------------------------------- 3. extraction

EXTRACT_PROMPT = """You are reading part of an earnings-call transcript of {company} (NSE: {symbol}).
The call took place in {call_date} and discusses {quarter}. Indian fiscal years run April-March:
FY27 = April 2026 to March 2027, Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar.

Below are ONLY statements by the company's management, each tagged with its page as [p.N].
Extract every forward-looking commitment or guidance that has a number or a dated event, e.g.
"EBITDA margin of 13-14% for FY27", "capex of Rs 600 crore this year", "new plant by Q4 FY27".

Rules:
- Skip descriptions of results already delivered ("we grew 15% this quarter").
- Skip vague statements with no number and no date ("we remain confident").
- verbatim_quote must be copied EXACTLY from the text, one or two sentences, no edits.
- page = the N of the [p.N] tag the quote comes from.
- deadline_fy is the 4-digit fiscal year end (FY27 -> 2027). Resolve "this year", "next year",
  "by March 2027" using the call date. deadline_q is 1-4 or null for a full-year target.
- target_low / target_high: numbers only (13-14% -> 13 and 14; "at least 20%" -> 20 and null).
- metric_key: revenue_growth, revenue (absolute, in Rs crore), ebitda_margin, ebitda_growth,
  pat_growth, pat (absolute, Rs crore), capex, capacity, volume_growth, debt, working_capital, other.
- At most 15 items. If there are none, return an empty list.

Return JSON: {{"items": [{{"metric", "metric_key", "target_text", "target_low", "target_high", "unit",
"deadline_text", "deadline_fy", "deadline_q", "speaker_name", "verbatim_quote", "page"}}]}}

TEXT:
{text}
"""


def _norm_text(t: str) -> str:
    t = t.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"-\s*\n\s*", "", t)
    return re.sub(r"\s+", " ", t).strip()


def quote_found(quote: str, page_texts: list[str], page: int) -> int | None:
    """Return the page the quote is on (page, or a neighbour), else None."""
    q = _norm_text(quote).strip(' "')
    if len(q) < 12:
        return None
    for p in (page, page - 1, page + 1):
        if 1 <= p <= len(page_texts):
            hay = _norm_text(page_texts[p - 1])
            if q in hay or fuzz.partial_ratio(q, hay) >= 92:
                return p
    # across a page break
    for p in (page - 1, page):
        if 1 <= p < len(page_texts):
            hay = _norm_text(page_texts[p - 1] + " " + page_texts[p])
            if q in hay or fuzz.partial_ratio(q, hay) >= 92:
                return p
    return None


def extract(sym: str, company: str, tr: dict, doc: dict, stats: dict) -> list[dict]:
    fl = forward_looking(doc)
    full = sum(approx_tokens(t["text"]) for t in doc["turns"])
    text = "\n".join(f"[p.{t['page']}] {t['speaker']}{' (' + t['title'] + ')' if t.get('title') else ''}: {t['text']}"
                     for t in fl)
    stats["tokens_full"] += full
    stats["tokens_sent"] += approx_tokens(text)
    if not text.strip():
        return []
    prompt = EXTRACT_PROMPT.format(company=company, symbol=sym, call_date=tr["date_label"],
                                   quarter=tr["quarter"], text=text[:60000])
    res = llm.cheap(prompt, step="promise_extract", schema=Extraction)
    titles = {t["speaker"]: t.get("title", "") for t in doc["turns"] if t.get("role") == "management"}
    out = []
    for it in res["items"]:
        stats["extracted"] += 1
        page = quote_found(it["verbatim_quote"], doc["page_texts"], it["page"])
        if page is None:
            stats["dropped_quote_not_found"] += 1
            continue
        it["page"] = page
        it["speaker_role"] = next((v for k, v in titles.items() if fuzz.token_set_ratio(k, it["speaker_name"]) >= 85), "")
        it.update({"quarter_said": tr["quarter"], "qidx_said": qindex(tr["fy"], tr["q"]),
                   "call_date": tr["date_label"], "transcript_url": tr["url"]})
        out.append(it)
    return out


# ---------------------------------------------------------------- 5. linking

def _deadline_idx(p: dict) -> int | None:
    if not p.get("deadline_fy"):
        return None
    return qindex(p["deadline_fy"], p.get("deadline_q") or 4)


def _same_thread(a: dict, b: dict) -> bool:
    if a["metric_key"] != b["metric_key"]:
        return False
    if (a.get("deadline_fy"), a.get("deadline_q")) != (b.get("deadline_fy"), b.get("deadline_q")):
        return False
    if a["metric_key"] in ("other", "capacity", "capex", "volume_growth"):
        return fuzz.token_set_ratio(a["metric"], b["metric"]) >= 70
    return True


def link(items: list[dict], call_idxs: list[int], sym: str) -> list[dict]:
    threads: list[dict] = []
    for it in sorted(items, key=lambda x: x["qidx_said"]):
        th = next((t for t in threads if _same_thread(t["mentions"][-1], it)), None)
        if th and th["mentions"][-1]["qidx_said"] == it["qidx_said"]:
            continue  # same promise twice in one call: keep the first
        if th is None:
            th = {"mentions": []}
            threads.append(th)
        th["mentions"].append(it)

    newest = sorted(set(call_idxs), reverse=True)
    latest_two = set(newest[:2])
    out = []
    for i, th in enumerate(threads, start=1):
        m = th["mentions"]
        last = m[-1]
        lows = [x.get("target_low") for x in m]
        revised, direction = False, None
        for a, b in zip(lows, lows[1:]):
            if a is not None and b is not None and abs(a - b) > 1e-6:
                revised, direction = True, ("up" if b > a else "down")
        dl = _deadline_idx(last)
        dropped = (len(newest) >= 3 and last["qidx_said"] not in latest_two
                   and (dl is None or dl > newest[0]))
        out.append({
            "id": f"{sym}-{i}",
            "metric": last["metric"], "metric_key": last["metric_key"], "unit": last.get("unit", ""),
            "deadline_fy": last.get("deadline_fy"), "deadline_q": last.get("deadline_q"),
            "deadline": (qlabel(last["deadline_fy"], last.get("deadline_q")) if last.get("deadline_fy")
                         else (last.get("deadline_text") or "no date")),
            "target_text": last["target_text"], "target_low": last.get("target_low"), "target_high": last.get("target_high"),
            "first_said": m[0]["quarter_said"], "times_said": len(m),
            "revised": revised, "revision_direction": direction, "quietly_dropped": dropped,
            "speakers": sorted({x["speaker_name"] for x in m}),
            "mentions": [{k: x.get(k) for k in ("quarter_said", "call_date", "target_text", "target_low", "target_high",
                                                 "speaker_name", "speaker_role", "verbatim_quote", "page", "transcript_url")}
                         for x in m],
        })
    return out


# ---------------------------------------------------------------- 6. settle in code

def _actuals(f: dict) -> tuple[dict, dict, int | None]:
    q = {qindex(r["fy"], r["q"]): r for r in f["quarterly"] if r.get("revenue") is not None}
    a = {r["fy"]: r for r in f["annual"] if r.get("revenue") is not None}
    return q, a, (max(q) if q else None)


def _margin(r: dict) -> float | None:
    e = r.get("ebitda") if r.get("ebitda") is not None else r.get("financing_profit")
    if e is None or not r.get("revenue"):
        return r.get("opm")
    return round(e / r["revenue"] * 100, 1)


def _growth(cur: dict | None, prev: dict | None, key: str) -> float | None:
    if not cur or not prev or cur.get(key) is None or not prev.get(key):
        return None
    return round((cur[key] - prev[key]) / abs(prev[key]) * 100, 1)


def _fy_sum(q: dict, fy: int, key: str, upto_q: int = 4) -> float | None:
    vals = [q.get(qindex(fy, i), {}).get(key) for i in range(1, upto_q + 1)]
    return sum(vals) if all(v is not None for v in vals) else None


def actual_for(th: dict, q: dict, a: dict) -> tuple[float | None, str]:
    """The reported number that settles this promise, if code can compute it."""
    key, fy, qq = th["metric_key"], th.get("deadline_fy"), th.get("deadline_q")
    if not fy:
        return None, ""
    field = {"revenue_growth": "revenue", "revenue": "revenue", "pat_growth": "pat", "pat": "pat",
             "ebitda_growth": "ebitda"}.get(key)
    if qq:
        cur, prev = q.get(qindex(fy, qq)), q.get(qindex(fy - 1, qq))
        where = qlabel(fy, qq)
        if key == "ebitda_margin" and cur:
            v = _margin(cur)
            return v, f"{v}% in {where}" if v is not None else ""
        if key in ("revenue_growth", "pat_growth", "ebitda_growth"):
            v = _growth(cur, prev, field)
            return v, f"{v:+.1f}% YoY in {where}" if v is not None else ""
        if key in ("revenue", "pat") and cur and cur.get(field) is not None:
            return cur[field], f"Rs {cur[field]:,.0f} cr in {where}"
        return None, ""
    cur, prev = a.get(fy), a.get(fy - 1)
    if cur is None:  # annual table not updated yet: build from quarters
        s = {k: _fy_sum(q, fy, k) for k in ("revenue", "pat", "ebitda")}
        cur = s if s["revenue"] is not None else None
    if prev is None:
        s = {k: _fy_sum(q, fy - 1, k) for k in ("revenue", "pat", "ebitda")}
        prev = s if s["revenue"] is not None else None
    where = qlabel(fy)
    if key == "ebitda_margin" and cur:
        v = _margin(cur)
        return v, f"{v}% in {where}" if v is not None else ""
    if key in ("revenue_growth", "pat_growth", "ebitda_growth"):
        v = _growth(cur, prev, field)
        return v, f"{v:+.1f}% in {where}" if v is not None else ""
    if key in ("revenue", "pat") and cur and cur.get(field) is not None:
        return cur[field], f"Rs {cur[field]:,.0f} cr in {where}"
    return None, ""


def progress_for(th: dict, q: dict, latest: int | None) -> str:
    """For a pending full-year target: how the year is going so far."""
    fy, key = th.get("deadline_fy"), th["metric_key"]
    if not fy or th.get("deadline_q") or latest is None:
        return ""
    done = [i for i in range(1, 5) if qindex(fy, i) in q]
    if not done or len(done) == 4:
        return ""
    n = max(done)
    if key in ("revenue_growth", "pat_growth"):
        f = "revenue" if key == "revenue_growth" else "pat"
        cur, prev = _fy_sum(q, fy, f, n), _fy_sum(q, fy - 1, f, n)
        if cur is not None and prev:
            g = (cur - prev) / abs(prev) * 100
            return f"{'Q1' if n == 1 else 'H1' if n == 2 else '9M'} FY{fy % 100:02d}: {g:+.1f}%"
    if key == "ebitda_margin":
        rows = [q[qindex(fy, i)] for i in range(1, n + 1)]
        rev = sum(r["revenue"] for r in rows)
        e = sum((r.get("ebitda") or 0) for r in rows)
        if rev:
            return f"{'Q1' if n == 1 else 'H1' if n == 2 else '9M'} FY{fy % 100:02d}: {e / rev * 100:.1f}%"
    return ""


def settle_in_code(threads: list[dict], f: dict) -> None:
    q, a, latest = _actuals(f)
    for th in threads:
        th["status"], th["actual_text"], th["reason"], th["settled_by"] = "pending", "", "", "code"
        dl = _deadline_idx(th)
        if dl is None:
            th["status"], th["settled_by"] = "unverifiable", "code"
            th["reason"] = "No date was given."
            continue
        if latest is None or dl > latest:
            th["progress"] = progress_for(th, q, latest)
            continue  # deadline not reached yet
        val, txt = actual_for(th, q, a)
        if val is None or th.get("target_low") is None:
            th["status"], th["settled_by"] = "needs_judgment", "model"
            continue
        low, high = th["target_low"], th.get("target_high")
        if th["metric_key"] in ("revenue", "pat") and "cr" not in (th.get("unit") or "").lower() and "crore" not in th["target_text"].lower():
            th["status"], th["settled_by"] = "needs_judgment", "model"
            continue
        kept = val >= low
        th["status"] = "kept" if kept else "missed"
        th["actual_text"] = txt
        gap = val - low
        unit = "pp" if th["metric_key"] in ("ebitda_margin", "revenue_growth", "pat_growth", "ebitda_growth") else ""
        th["reason"] = (f"Target {th['target_text']}; delivered {txt}." if kept
                        else f"Target {th['target_text']}; delivered {txt}, short by {abs(gap):,.1f}{unit}.")


# ---------------------------------------------------------------- 7. strong model

def _numbers_table(f: dict) -> str:
    rows = ["quarter | revenue cr | ebitda cr | ebitda margin % | pat cr"]
    for r in f["quarterly"][-8:]:
        e = r.get("ebitda") if r.get("ebitda") is not None else r.get("financing_profit")
        rows.append(f"{r['quarter']} | {r.get('revenue')} | {e} | {_margin(r)} | {r.get('pat')}")
    rows.append("year | revenue cr | ebitda cr | pat cr | cash from operations cr")
    for r in f["annual"][-5:]:
        rows.append(f"{r['label']} | {r.get('revenue')} | {r.get('ebitda')} | {r.get('pat')} | {r.get('cfo')}")
    return "\n".join(rows)


def judge(threads: list[dict], f: dict) -> str:
    if not threads:
        return ""
    lines = []
    for t in threads:
        lines.append(f"{t['id']} | {t['metric']} | target {t['target_text']} | by {t['deadline']} | "
                     f"said {t['times_said']}x from {t['first_said']} | code status: {t['status']} "
                     f"{t.get('actual_text', '')} | revised: {t['revised']} {t['revision_direction'] or ''} | "
                     f"dropped from recent calls: {t['quietly_dropped']}")
    need = [t["id"] for t in threads if t["status"] == "needs_judgment"]
    prompt = (
        f"Company: {f['name']} ({f['symbol']}). Promise ledger from the last {N_CALLS} earnings calls, "
        "and reported numbers (from company filings via screener.in).\n"
        "Use ONLY the information below. No outside knowledge of this company.\n\n"
        f"PROMISES\n" + "\n".join(lines) + f"\n\nREPORTED NUMBERS\n{_numbers_table(f)}\n\n"
        f"1. Give a verdict for these ids only: {need or 'none'}. status = kept / missed / pending / unverifiable. "
        "Use unverifiable when these numbers can't settle it (e.g. capacity, plant dates). "
        "actual_text = the number you used, or ''. reason = one short line.\n"
        "2. summary: at most 70 words on where management's story and the numbers agree or diverge. "
        "Plain words. Mention misses, revisions and dropped items if any. No praise words.\n"
        'Return JSON: {"verdicts": [{"id", "status", "actual_text", "reason"}], "summary": "..."}'
    )
    res = llm.strong(prompt, step="promise_verdicts", schema=Verdicts)
    by_id = {v["id"]: v for v in res["verdicts"]}
    for t in threads:
        if t["status"] == "needs_judgment":
            v = by_id.get(t["id"])
            if v:
                t.update({"status": v["status"], "actual_text": v["actual_text"], "reason": v["reason"], "settled_by": "model"})
            else:
                t.update({"status": "unverifiable", "reason": "Could not be settled from reported numbers."})
    return res["summary"]


def display_status(t: dict) -> str:
    if t["status"] in ("kept", "missed"):
        return t["status"]
    if t.get("quietly_dropped"):
        return "dropped"
    if t.get("revised"):
        return "revised"
    return t["status"]


# ---------------------------------------------------------------- main

def build(sym: str, progress: Callable[[str], None] = lambda m: None, refresh: bool = False) -> dict:
    sym = sym.upper().strip()
    out_path = OUT / f"{sym}.json"
    if not refresh and out_path.exists():
        return read_json(out_path)

    progress("Fetching company page from screener.in")
    f = fundamentals.get(sym)
    calls = f["transcripts"][:N_CALLS]
    stats = {"tokens_full": 0, "tokens_sent": 0, "extracted": 0, "dropped_quote_not_found": 0, "calls": len(calls)}
    if not calls:
        progress("No concall transcripts listed on screener.in")
    s = session()
    items, used, saved_turns = [], [], []
    for i, tr in enumerate(calls, start=1):
        progress(f"Reading transcript {i} of {len(calls)} ({tr['date_label']})")
        try:
            doc = load_transcript(tr["url"], s)
        except Exception as e:
            used.append({**tr, "readable": False, "error": str(e)[:120]})
            continue
        used.append({**tr, "readable": doc["readable"], "pages": doc["pages"],
                     "participants": doc.get("participants", [])})
        if not doc["readable"]:
            continue
        saved_turns.append({**tr, "turns": [t for t in doc["turns"] if t.get("role") == "management"],
                            "participants": doc.get("participants", [])})
        try:
            items.extend(extract(sym, f["name"], tr, doc, stats))
        except llm.LLMUnavailable:
            raise
        except llm.LLMError as e:
            log("promises", f"{sym} {tr['date_label']}: extraction failed: {str(e)[:100]}")
    write_json(TDIR / f"{sym}.json", {"symbol": sym, "calls": saved_turns})

    progress(f"{len(items)} promises found, linking them across calls")
    call_idxs = [qindex(t["fy"], t["q"]) for t in used if t.get("readable")]
    threads = link(items, call_idxs, sym)
    settle_in_code(threads, f)
    progress("Scoring promises against reported numbers")
    summary = ""
    try:
        summary = judge(threads, f)
    except (llm.LLMUnavailable, llm.LLMError) as e:
        log("promises", f"{sym}: verdict step skipped ({str(e)[:80]})")
        for t in threads:
            if t["status"] == "needs_judgment":
                t.update({"status": "unverifiable", "reason": "Not settled (model unavailable)."})
    for t in threads:
        t["display_status"] = display_status(t)

    kept = sum(1 for t in threads if t["status"] == "kept")
    missed = sum(1 for t in threads if t["status"] == "missed")
    ledger = {
        "symbol": sym, "company": f["name"], "as_of": iso(now_ist()),
        "transcripts": [{k: t.get(k) for k in ("date_label", "quarter", "url", "readable", "pages", "error")} for t in used],
        "threads": threads,
        "credibility": {"kept": kept, "missed": missed, "settled": kept + missed,
                        "score": round(kept / (kept + missed), 2) if kept + missed >= 3 else None},
        "counts": {s: sum(1 for t in threads if t["display_status"] == s)
                   for s in ("kept", "missed", "pending", "revised", "dropped", "unverifiable")},
        "summary": summary, "stats": stats,
    }
    write_json(out_path, ledger)
    return ledger


def print_ledger(L: dict) -> None:
    print(f"\n{L['company']} — {len(L['threads'])} promises, credibility {L['credibility']}")
    print(f"{'status':<12}{'by':<10}{'target':<26}{'delivered':<24}metric")
    for t in L["threads"]:
        print(f"{t['display_status']:<12}{t['deadline']:<10}{t['target_text'][:24]:<26}"
              f"{(t.get('actual_text') or t.get('progress') or '')[:22]:<24}{t['metric'][:40]}")
    s = L["stats"]
    print(f"tokens: {s['tokens_full']:,} in transcripts -> {s['tokens_sent']:,} sent "
          f"({100 - 100 * s['tokens_sent'] / max(s['tokens_full'], 1):.0f}% cut); "
          f"{s['extracted']} extracted, {s['dropped_quote_not_found']} dropped (quote not on page)")
    if L["summary"]:
        print("summary:", L["summary"])


if __name__ == "__main__":
    for sym in sys.argv[1:] or ["POLYCAB"]:
        print_ledger(build(sym, progress=lambda m: log("promises", m), refresh=True))
        c = llm.cost_summary()["total"]
        print(f"cost so far: Rs {c['inr']:.2f}, {c['calls']} calls, {c['cache_hits']} cache hits")

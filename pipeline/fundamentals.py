"""Company fundamentals from screener.in (which compiles them from company filings).

For any NSE symbol this gives us:
  - quarterly results (last ~12 quarters), annual P&L, cash flow, balance sheet, ratios
  - links to annual reports and concall transcripts (the primary documents)
  - the BSE scrip code (used as a fallback source for announcements)

Usage: python -m pipeline.fundamentals POLYCAB
"""
from __future__ import annotations

import re
import sys
import time

from bs4 import BeautifulSoup

from .common import (DATA, RAW, iso, log, now_ist, parse_month_year, polite,
                     quarter_discussed_on_call, quarter_of_period_end, qlabel,
                     session, to_number, write_json, read_json)

BASE = "https://www.screener.in/company/{sym}/{view}"
HTML_DIR = RAW / "screener"
OUT_DIR = DATA / "fundamentals"
MAX_AGE_S = 24 * 3600

ROW_KEYS = {
    "sales": "revenue", "revenue": "revenue", "revenue from operations": "revenue",
    "expenses": "expenses",
    "operating profit": "ebitda", "financing profit": "financing_profit",
    "opm %": "opm", "financing margin %": "financing_margin",
    "other income": "other_income", "interest": "interest", "depreciation": "depreciation",
    "profit before tax": "pbt", "tax %": "tax_pct", "net profit": "pat", "eps in rs": "eps",
    "cash from operating activity": "cfo", "cash from investing activity": "cfi",
    "cash from financing activity": "cff", "net cash flow": "net_cash",
    "equity capital": "equity_capital", "reserves": "reserves", "borrowings": "borrowings",
    "other liabilities": "other_liabilities", "total liabilities": "total_liabilities",
    "fixed assets": "fixed_assets", "cwip": "cwip", "investments": "investments",
    "other assets": "other_assets", "total assets": "total_assets", "deposits": "deposits",
    "debtor days": "debtor_days", "inventory days": "inventory_days", "days payable": "days_payable",
    "cash conversion cycle": "ccc", "working capital days": "wc_days", "roce %": "roce", "roe %": "roe",
    "gross npa %": "gnpa", "net npa %": "nnpa",
}


class ScreenerError(RuntimeError):
    pass


# ---------------------------------------------------------------- fetching

def _fetch(sym: str, view: str, s=None) -> str:
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    path = HTML_DIR / f"{sym}-{view.strip('/') or 'standalone'}.html"
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_S:
        return path.read_text()
    s = s or session(referer="https://www.screener.in/")
    url = BASE.format(sym=sym, view=view)
    for attempt in range(3):
        r = s.get(url, timeout=30)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 404:
            raise ScreenerError(f"{sym} not found on screener.in")
        r.raise_for_status()
        path.write_text(r.text)
        polite(1.5, 3.0)
        return r.text
    raise ScreenerError(f"screener.in kept rate-limiting {sym}")


# ---------------------------------------------------------------- parsing

def _clean_label(text: str) -> str:
    t = text.replace("\xa0", " ").replace("+", "").strip()
    return re.sub(r"\s+", " ", t)


def parse_table(section) -> dict:
    """Return {'periods': [...], 'rows': {key: [values]}, 'raw_rows': {label: [...]}}"""
    if section is None:
        return {"periods": [], "rows": {}, "raw_rows": {}}
    table = section.find("table")
    if table is None:
        return {"periods": [], "rows": {}, "raw_rows": {}}
    head = table.find("thead")
    periods = [_clean_label(th.get_text()) for th in head.find_all("th")][1:] if head else []
    rows, raw = {}, {}
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        label = _clean_label(tds[0].get_text())
        if not label or label.lower() == "raw pdf":
            continue
        vals = [to_number(td.get_text()) for td in tds[1:]]
        raw[label] = vals
        key = ROW_KEYS.get(label.lower())
        if key:
            rows[key] = vals
    return {"periods": periods, "rows": rows, "raw_rows": raw}


def _raw_pdf_links(section) -> list[str | None]:
    """Quarterly table has a 'Raw PDF' row linking each quarter's results filing."""
    if section is None or section.find("table") is None:
        return []
    for tr in section.find("table").find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if tds and _clean_label(tds[0].get_text()).lower() == "raw pdf":
            out = []
            for td in tds[1:]:
                a = td.find("a")
                href = a.get("href") if a else None
                if href and href.startswith("/"):
                    href = "https://www.screener.in" + href
                out.append(href)
            return out
    return []


def _documents(soup) -> tuple[list[dict], list[dict]]:
    transcripts, reports = [], []
    for a in soup.find_all("a"):
        text = _clean_label(a.get_text())
        href = a.get("href") or ""
        if text.lower() == "transcript" and href:
            li = a.find_parent("li")
            mt = parse_month_year(li.get_text(" ") if li else "")
            if not mt:
                continue
            month, year = mt
            fy, q = quarter_discussed_on_call(month, year)
            transcripts.append({
                "date_label": f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]} {year}",
                "month": month, "year": year, "fy": fy, "q": q, "quarter": qlabel(fy, q), "url": href,
            })
        m = re.match(r"Financial Year (\d{4})", text)
        if m and href.startswith("http"):
            reports.append({"fy": int(m.group(1)), "label": f"Annual report FY{int(m.group(1)) % 100:02d}", "url": href})
    # newest first, de-duplicated
    seen, tr = set(), []
    for t in sorted(transcripts, key=lambda t: (t["year"], t["month"]), reverse=True):
        if t["url"] not in seen:
            seen.add(t["url"])
            tr.append(t)
    seen, ar = set(), []
    for r in sorted(reports, key=lambda r: r["fy"], reverse=True):
        if r["url"] not in seen:
            seen.add(r["url"])
            ar.append(r)
    return tr, ar


def _top_ratios(soup) -> dict:
    out = {}
    ul = soup.find(id="top-ratios")
    if not ul:
        return out
    for li in ul.find_all("li"):
        name = li.find(class_="name")
        num = li.find(class_="number")
        if name and num:
            out[_clean_label(name.get_text())] = to_number(num.get_text())
    return out


def _period_to_quarter(label: str) -> tuple[int, int] | None:
    mt = parse_month_year(label)
    if not mt:
        return None
    return quarter_of_period_end(*mt)


def normalise_quarters(t: dict) -> list[dict]:
    out = []
    rows = t["rows"]
    for i, label in enumerate(t["periods"]):
        fq = _period_to_quarter(label)
        if not fq:
            continue
        def g(k):
            v = rows.get(k)
            return v[i] if v and i < len(v) else None
        out.append({
            "period": label, "fy": fq[0], "q": fq[1], "quarter": qlabel(*fq),
            "revenue": g("revenue"), "ebitda": g("ebitda"), "financing_profit": g("financing_profit"),
            "opm": g("opm") if g("opm") is not None else g("financing_margin"),
            "other_income": g("other_income"), "interest": g("interest"),
            "depreciation": g("depreciation"), "pbt": g("pbt"), "pat": g("pat"), "eps": g("eps"),
        })
    return out


def normalise_annual(pl: dict, cf: dict, bs: dict, ratios: dict) -> list[dict]:
    def by_year(t):
        m = {}
        for i, label in enumerate(t["periods"]):
            if label.upper() == "TTM":
                continue
            mt = parse_month_year(label)
            if not mt:
                continue
            fy = mt[1] if mt[0] <= 3 else mt[1] + 1  # Mar 2025 -> FY25
            m[fy] = {k: (v[i] if i < len(v) else None) for k, v in t["rows"].items()}
        return m
    P, C, B, R = by_year(pl), by_year(cf), by_year(bs), by_year(ratios)
    years = sorted(set(P) | set(C))
    out = []
    for fy in years:
        p, c, b, r = P.get(fy, {}), C.get(fy, {}), B.get(fy, {}), R.get(fy, {})
        equity = None
        if b.get("equity_capital") is not None and b.get("reserves") is not None:
            equity = b["equity_capital"] + b["reserves"]
        out.append({
            "fy": fy, "label": qlabel(fy),
            "revenue": p.get("revenue"), "ebitda": p.get("ebitda"), "financing_profit": p.get("financing_profit"),
            "opm": p.get("opm") if p.get("opm") is not None else p.get("financing_margin"),
            "pbt": p.get("pbt"), "pat": p.get("pat"),
            "cfo": c.get("cfo"), "cfi": c.get("cfi"), "cff": c.get("cff"),
            "borrowings": b.get("borrowings"), "equity": equity, "total_assets": b.get("total_assets"),
            "cwip": b.get("cwip"),
            "debtor_days": r.get("debtor_days"), "inventory_days": r.get("inventory_days"),
            "days_payable": r.get("days_payable"), "ccc": r.get("ccc"), "wc_days": r.get("wc_days"),
            "roce": r.get("roce") if r.get("roce") is not None else r.get("roe"),
        })
    return out


def parse(html: str, sym: str, view: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    name = _clean_label(h1.get_text()) if h1 else sym
    about_el = soup.select_one(".company-profile .about") or soup.select_one(".about")
    about = _clean_label(about_el.get_text(" ")) if about_el else ""
    text = soup.get_text(" ")
    bse = re.search(r"BSE:\s*(\d{6})", text)
    nse = re.search(r"NSE:\s*([A-Z0-9&\-]+)", text)

    q_sec = soup.find(id="quarters")
    quarters = parse_table(q_sec)
    pl = parse_table(soup.find(id="profit-loss"))
    cf = parse_table(soup.find(id="cash-flow"))
    bs = parse_table(soup.find(id="balance-sheet"))
    ratios = parse_table(soup.find(id="ratios"))
    transcripts, reports = _documents(soup)
    lender = "financing_profit" in quarters["rows"] or "financing_profit" in pl["rows"]

    qn = normalise_quarters(quarters)
    pdfs = _raw_pdf_links(q_sec)
    for i, q in enumerate(qn):
        q["filing_url"] = pdfs[i] if i < len(pdfs) else None

    return {
        "symbol": sym, "name": name, "view": view or "standalone", "url": url,
        "bse_code": bse.group(1) if bse else None, "nse_code": nse.group(1) if nse else sym,
        "about": about[:1200], "top_ratios": _top_ratios(soup),
        "company_type": "lender" if lender else "corporate",
        "quarterly": qn,
        "annual": normalise_annual(pl, cf, bs, ratios),
        "transcripts": transcripts, "annual_reports": reports,
        "fetched_at": iso(now_ist()),
    }


def _has_numbers(f: dict) -> bool:
    return sum(1 for q in f["quarterly"] if q.get("revenue") is not None) >= 4


def get(sym: str, s=None, refresh: bool = False) -> dict:
    """Fetch + parse, consolidated first, standalone as fallback. Cached for 24h."""
    sym = sym.upper().strip()
    out_path = OUT_DIR / f"{sym}.json"
    cached = read_json(out_path)
    if cached and not refresh:
        return cached
    s = s or session(referer="https://www.screener.in/")
    last = None
    for view in ("consolidated/", ""):
        url = BASE.format(sym=sym, view=view)
        try:
            f = parse(_fetch(sym, view, s), sym, view.strip("/") or "standalone", url)
        except ScreenerError as e:
            last = e
            continue
        if _has_numbers(f):
            write_json(out_path, f)
            return f
        last = ScreenerError(f"{sym}: {view or 'standalone'} view had no quarterly numbers")
    raise last or ScreenerError(sym)


def run(symbols: list[str]) -> dict:
    s = session(referer="https://www.screener.in/")
    ok, failed = {}, []
    for sym in symbols:
        try:
            f = get(sym, s, refresh=True)
            ok[sym] = f
            log("fundamentals", f"{sym}: {f['view']}, {len(f['quarterly'])} quarters, "
                f"{len(f['transcripts'])} transcripts, {f['company_type']}")
        except Exception as e:
            failed.append(sym)
            log("fundamentals", f"{sym}: FAILED {e}")
    return {"ok": ok, "failed": failed}


def print_quarters(f: dict) -> None:
    print(f"\n{f['name']} ({f['symbol']}, {f['view']}, {f['company_type']})")
    print(f"{'quarter':<10}{'revenue':>11}{'ebitda':>10}{'opm%':>6}{'pbt':>10}{'pat':>10}")
    for q in f["quarterly"][-8:]:
        e = q["ebitda"] if q["ebitda"] is not None else q["financing_profit"]
        print(f"{q['quarter']:<10}{q['revenue'] or 0:>11,.0f}{e or 0:>10,.0f}{q['opm'] or 0:>6.0f}"
              f"{q['pbt'] or 0:>10,.0f}{q['pat'] or 0:>10,.0f}")


if __name__ == "__main__":
    for sym in sys.argv[1:] or ["POLYCAB"]:
        print_quarters(get(sym, refresh=True))

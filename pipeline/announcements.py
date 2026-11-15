"""Corporate announcements for every holding.

NSE first (it needs cookies from the homepage, so we open a session there first).
If NSE fails for a symbol, BSE is used instead (scrip code comes from screener.in,
or from config/bse_codes.yaml if you want to set it by hand).

Writes data/announcements.json and keeps raw responses in data/raw/ann/.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from .common import (CONFIG, DATA, IST, RAW, iso, load_yaml, log, now_ist, polite,
                     portfolio, read_json, session, write_json)

NSE_HOME = "https://www.nseindia.com/"
NSE_API = ("https://www.nseindia.com/api/corporate-announcements?index=equities"
           "&symbol={sym}&from_date={frm}&to_date={to}")
BSE_API = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno={page}"
           "&strCat=-1&strPrevDate={frm}&strScrip={code}&strSearch=P&strToDate={to}&strType=C&subcategory=-1")
BSE_PDF = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}"
RAW_DIR = RAW / "ann"


class Nse:
    """One warmed-up session shared across symbols."""

    def __init__(self):
        self.s = session(referer="https://www.nseindia.com/companies-listing/corporate-filings-announcements")
        self.warm = False

    def warm_up(self):
        if self.warm:
            return
        self.s.get(NSE_HOME, timeout=20)
        polite(1, 2)
        self.s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=20)
        self.warm = True

    def fetch(self, sym: str, frm: datetime, to: datetime) -> list[dict]:
        self.warm_up()
        url = NSE_API.format(sym=sym.replace("&", "%26"), frm=frm.strftime("%d-%m-%Y"), to=to.strftime("%d-%m-%Y"))
        r = self.s.get(url, timeout=30)
        if r.status_code in (401, 403):
            # cookies expired: warm up again once
            self.warm = False
            self.warm_up()
            r = self.s.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            data = data.get("data", [])
        return data


def _nse_time(item: dict) -> str | None:
    for key, fmt in (("sort_date", "%Y-%m-%d %H:%M:%S"), ("an_dt", "%d-%b-%Y %H:%M:%S"),
                     ("exchdisstime", "%d-%b-%Y %H:%M:%S"), ("dt", "%d%m%Y%H%M%S")):
        v = item.get(key)
        if not v:
            continue
        try:
            return iso(datetime.strptime(str(v).strip(), fmt).replace(tzinfo=IST))
        except ValueError:
            continue
    return None


def normalise_nse(sym: str, item: dict) -> dict:
    subject = (item.get("attchmntText") or item.get("desc") or "").strip()
    seq = item.get("seq_id") or hashlib.sha1(str(item).encode()).hexdigest()[:12]
    return {
        "id": f"nse-{seq}",
        "symbol": sym,
        "company": item.get("sm_name") or sym,
        "time": _nse_time(item),
        "exchange_category": (item.get("desc") or "").strip(),
        "subject": subject,
        "url": item.get("attchmntFile") or None,
        "source": "nse",
    }


def fetch_bse(code: str, frm: datetime, to: datetime) -> list[dict]:
    s = session(referer="https://www.bseindia.com/")
    s.headers["Origin"] = "https://www.bseindia.com"
    rows = []
    for page in range(1, 6):
        url = BSE_API.format(page=page, frm=frm.strftime("%Y%m%d"), to=to.strftime("%Y%m%d"), code=code)
        r = s.get(url, timeout=30)
        r.raise_for_status()
        table = r.json().get("Table", [])
        if not table:
            break
        rows.extend(table)
        if len(table) < 50:
            break
        polite(0.8, 1.5)
    return rows


def normalise_bse(sym: str, item: dict) -> dict:
    t = item.get("NEWS_DT") or item.get("DT_TM")
    when = None
    if t:
        try:
            when = iso(datetime.fromisoformat(str(t)[:19]).replace(tzinfo=IST))
        except ValueError:
            pass
    cat = " - ".join(x for x in (item.get("CATEGORYNAME"), item.get("SUBCATNAME")) if x and x != "-")
    name = item.get("ATTACHMENTNAME")
    return {
        "id": f"bse-{item.get('NEWSID') or hashlib.sha1(str(item).encode()).hexdigest()[:12]}",
        "symbol": sym,
        "company": item.get("SLONGNAME") or sym,
        "time": when,
        "exchange_category": cat,
        "subject": (item.get("HEADLINE") or item.get("NEWSSUB") or "").strip(),
        "url": BSE_PDF.format(name=name) if name else None,
        "source": "bse",
    }


def _bse_code(sym: str) -> str | None:
    manual = CONFIG / "bse_codes.yaml"
    if manual.exists():
        m = load_yaml("bse_codes.yaml") or {}
        if sym in m:
            return str(m[sym])
    f = read_json(DATA / "fundamentals" / f"{sym}.json")
    return f.get("bse_code") if f else None


def run(symbols: list[str] | None = None) -> dict:
    cfg = portfolio()
    symbols = symbols or [h["symbol"] for h in cfg["holdings"]]
    to = now_ist()
    frm = to - timedelta(days=cfg.get("lookback_days", 14))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    nse = Nse()
    items, report = [], {}
    for sym in symbols:
        got, source, err = [], None, None
        try:
            raw = nse.fetch(sym, frm, to)
            write_json(RAW_DIR / f"{sym}-nse.json", raw)
            got = [normalise_nse(sym, x) for x in raw]
            source = "nse"
        except Exception as e:
            err = f"nse: {str(e)[:80]}"
            code = _bse_code(sym)
            if code:
                try:
                    raw = fetch_bse(code, frm, to)
                    write_json(RAW_DIR / f"{sym}-bse.json", raw)
                    got = [normalise_bse(sym, x) for x in raw]
                    source = "bse"
                except Exception as e2:
                    err += f" | bse: {str(e2)[:80]}"
            else:
                err += " | bse: no scrip code"
        # dedupe inside one source
        seen, clean = set(), []
        for it in got:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            clean.append(it)
        items.extend(clean)
        report[sym] = {"count": len(clean), "source": source, "error": err if not source else None}
        log("announcements", f"{sym}: {len(clean)} via {source or 'NONE'}" + (f"  ({err})" if not source else ""))
        polite(0.8, 1.6)

    items.sort(key=lambda x: x["time"] or "", reverse=True)
    out = {"as_of": iso(to), "from": iso(frm), "items": items, "report": report}
    write_json(DATA / "announcements.json", out)
    empty = [s for s, r in report.items() if r["count"] == 0]
    if empty:
        print("symbols with zero filings in the window:", ", ".join(empty))
    return out


if __name__ == "__main__":
    run()

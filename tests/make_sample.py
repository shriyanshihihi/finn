"""Build a SAMPLE snapshot with made-up companies, fully offline.

It runs the real pipeline code (screener parser, transcript linking, ledger
settlement, results cards, management cards, digest export) but swaps the network
and the models for canned answers. Two reasons:
  1. it proves every code path works end to end without internet
  2. the web app gets data in the exact real shape to be built against

Every company here is fictional and the app shows a "Sample data" banner.
A real `python -m pipeline.run_all` replaces all of it.

    python tests/make_sample.py
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FINN_DATA"] = tempfile.mkdtemp(prefix="finn-sample-")
os.environ.pop("GEMINI_API_KEY", None)
os.environ["GEMINI_API_KEY"] = "sample-offline"   # makes llm.available() true; calls are faked below

import pandas as pd  # noqa: E402

from pipeline import (build_digest, classify, common, fundamentals, llm, prices,  # noqa: E402
                      promises, research, signals)
from pipeline.common import DATA, IST, WEB_DATA, write_json  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "screener_sample.html"
NOW = datetime.now(IST)

COMPANIES = {
    "NORTHWIND": {"name": "Northwind Cables Ltd (sample)", "sector": "Cables & wires", "scale": 1.0},
    "KESTREL": {"name": "Kestrel Electronics Ltd (sample)", "sector": "Electronics manufacturing", "scale": 0.55},
    "HARBOUR": {"name": "Harbour Finance Ltd (sample)", "sector": "NBFC", "scale": 1.3, "lender": True},
    "SUMMIT": {"name": "Summit Pharma Ltd (sample)", "sector": "Pharma", "scale": 1.4},
    "BLUEPEAK": {"name": "Bluepeak Paints Ltd (sample)", "sector": "Consumer", "scale": 1.8},
    "ORBIT": {"name": "Orbit Infotech Ltd (sample)", "sector": "IT services", "scale": 2.5},
    "TALLGRASS": {"name": "Tallgrass Foods Ltd (sample)", "sector": "FMCG", "scale": 0.8},
    "IRONBRIDGE": {"name": "Ironbridge Engineering Ltd (sample)", "sector": "Capital goods", "scale": 3.1},
}

PORTFOLIO = {
    "holdings": [{"symbol": s, "sector": c["sector"]} for s, c in COMPANIES.items()],
    "research": ["NORTHWIND", "KESTREL"],
    "ledger_for_holdings": False,
    "lookback_days": 14,
    "alerts": {"volume_multiple": 2.0, "move_pct": 4.0, "overrides": {"KESTREL": {"move_pct": 7.0}}},
    "watched_categories": ["results", "management_change", "M&A", "fund_raise", "pledging",
                           "insider_trading", "credit_rating", "litigation", "capex"],
    "pillars": {
        "NORTHWIND": [
            {"id": "nw-growth", "label": "Revenue keeps growing fast", "type": "metric", "metric": "revenue_yoy", "op": ">=", "value": 15},
            {"id": "nw-margin", "label": "Margins hold at 14%", "type": "metric", "metric": "ebitda_margin", "op": ">=", "value": 14},
            {"id": "nw-pledge", "label": "Promoter doesn't pledge", "type": "event", "category": "pledging"},
        ],
        "KESTREL": [
            {"id": "ks-cash", "label": "Profits turn into cash", "type": "metric", "metric": "cfo_to_pat", "op": ">=", "value": 0.7},
        ],
        "HARBOUR": [
            {"id": "hb-pat", "label": "Earnings keep compounding", "type": "metric", "metric": "pat_yoy", "op": ">=", "value": 10},
            {"id": "hb-mgmt", "label": "Leadership stays stable", "type": "event", "category": "management_change"},
        ],
        "TALLGRASS": [
            {"id": "tg-pledge", "label": "Promoter doesn't pledge", "type": "event", "category": "pledging"},
        ],
    },
}


def fake_portfolio():
    return PORTFOLIO


for mod in (common, build_digest, research, prices):
    if hasattr(mod, "portfolio"):
        mod.portfolio = fake_portfolio


# ---------------------------------------------------------------- fake screener pages

def page_for(sym: str) -> str:
    c = COMPANIES[sym]
    html = FIX.read_text()

    def scale(m):
        v = m.group(1).replace(",", "")
        neg = v.startswith("-")
        try:
            x = float(v) * c["scale"]
        except ValueError:
            return m.group(0)
        return f"<td>{x:,.0f}</td>" if not neg else f"<td>{x:,.0f}</td>"

    # scale money cells, leave % cells alone
    html = re.sub(r"<td>(-?[\d,]+)</td>", scale, html)
    html = html.replace("Sample Cables Ltd", c["name"]).replace("SAMPLECAB", sym)
    if c.get("lender"):
        html = (html.replace("Sales&nbsp;", "Revenue&nbsp;").replace(">Sales +<", ">Revenue +<")
                .replace("Operating Profit", "Financing Profit").replace("OPM %", "Financing Margin %"))
    return html


fundamentals._fetch = lambda sym, view, s=None: page_for(sym)


# ---------------------------------------------------------------- fake transcripts

CALLS = {
    "Jan 2026": [
        "Northwind Cables Q3 FY26 Earnings Call\nMANAGEMENT: MR. ARJUN MEHTA – MANAGING DIRECTOR\nMR. RAVI SHAH – CHIEF FINANCIAL OFFICER\n"
        "Moderator: Welcome to the call. I hand over to Mr. Arjun Mehta.\n",
        "Arjun Mehta: Thank you. We are a wires and cables company with a growing fast moving electricals business. "
        "Wires and cables are about 88% of revenue and FMEG is 10%. We expect revenue growth of at least 12% for FY26.\n",
        "Ravi Shah: We are targeting EBITDA margin of 14% by FY28.\nArjun Mehta: We will double our B2C capacity by FY28.\n"
        "Moderator: The first question is from the line of Karan Jain from XYZ Capital.\nKaran Jain: What about copper prices?\n"
        "Ravi Shah: Copper is volatile and we pass it through with a lag.\n",
    ],
    "May 2026": [
        "Northwind Cables Q4 FY26 Earnings Call\nMANAGEMENT: MR. ARJUN MEHTA – MANAGING DIRECTOR\nMR. RAVI SHAH – CHIEF FINANCIAL OFFICER\n"
        "Moderator: Welcome to the call.\n",
        "Ravi Shah: For Q2 FY27 we expect EBITDA margin of 13.5%. Arjun Mehta: We expect Q1 FY27 revenue to grow at least 18% year on year.\n",
        "Ravi Shah: We remain on track for 14% EBITDA margin by FY28.\n",
    ],
    "Jul 2026": [
        "Northwind Cables Q1 FY27 Earnings Call\nMANAGEMENT: MR. ARJUN MEHTA – MANAGING DIRECTOR\nMR. RAVI SHAH – CHIEF FINANCIAL OFFICER\n"
        "Moderator: Welcome to the call.\n",
        "Arjun Mehta: We expect revenue growth of 15% for FY27.\n",
        "Arjun Mehta: Demand from real estate and power transmission stayed healthy.\n",
        "Ravi Shah: Capex for FY27 will be Rs 600 crore.\n",
    ],
    "Oct 2026": [
        "Northwind Cables Q2 FY27 Earnings Call\nMANAGEMENT: MR. ARJUN MEHTA – MANAGING DIRECTOR\nMR. RAVI SHAH – CHIEF FINANCIAL OFFICER\n"
        "Moderator: Welcome to the call. I hand over to Mr. Arjun Mehta.\n",
        "Arjun Mehta: Wires and cables grew 16% and FMEG grew 9% this quarter. Ravi Shah: We now expect EBITDA margin of 13% by FY28.\n",
        "Arjun Mehta: We expect revenue growth of 15% for FY27. The new Halol plant will be commissioned in Q3 FY27.\n"
        "Moderator: The first question is from the line of Priya S from DEF Securities.\nPriya S: Why did margins fall?\n"
        "Ravi Shah: Competitive intensity in FMEG went up and we chose to hold prices.\n",
    ],
}


def fake_load_transcript(url, s=None):
    from pipeline.transcripts import parse
    label = {"t-oct26": "Oct 2026", "t-jul26": "Jul 2026", "t-may26": "May 2026", "t-jan26": "Jan 2026"}
    key = next((v for k, v in label.items() if k in url), None)
    texts = CALLS.get(key, ["empty"])
    doc = {"url": url, "pages": len(texts), "readable": key is not None, "page_texts": texts}
    doc.update(parse(texts) if key else {"participants": [], "turns": []})
    return doc


promises.load_transcript = fake_load_transcript


# ---------------------------------------------------------------- fake models

def P(metric, key, text, low, high, unit, fy, q, speaker, quote, page, dl=""):
    return {"metric": metric, "metric_key": key, "target_text": text, "target_low": low, "target_high": high,
            "unit": unit, "deadline_text": dl, "deadline_fy": fy, "deadline_q": q, "speaker_name": speaker,
            "verbatim_quote": quote, "page": page}


EXTRACT = {
    ("NORTHWIND", "Jan 2026"): [
        P("Revenue growth", "revenue_growth", "at least 12%", 12, None, "%", 2026, None, "Arjun Mehta",
          "We expect revenue growth of at least 12% for FY26.", 2),
        P("EBITDA margin", "ebitda_margin", "14%", 14, None, "%", 2028, None, "Ravi Shah",
          "We are targeting EBITDA margin of 14% by FY28.", 3),
        P("B2C capacity", "capacity", "2x", 2, None, "x", 2028, None, "Arjun Mehta",
          "We will double our B2C capacity by FY28.", 3),
    ],
    ("NORTHWIND", "May 2026"): [
        P("EBITDA margin", "ebitda_margin", "13.5%", 13.5, None, "%", 2027, 2, "Ravi Shah",
          "For Q2 FY27 we expect EBITDA margin of 13.5%.", 2),
        P("Revenue growth", "revenue_growth", "at least 18% YoY", 18, None, "%", 2027, 1, "Arjun Mehta",
          "We expect Q1 FY27 revenue to grow at least 18% year on year.", 2),
        P("EBITDA margin", "ebitda_margin", "14%", 14, None, "%", 2028, None, "Ravi Shah",
          "We remain on track for 14% EBITDA margin by FY28.", 3),
    ],
    ("NORTHWIND", "Jul 2026"): [
        P("Revenue growth", "revenue_growth", "15%", 15, None, "%", 2027, None, "Arjun Mehta",
          "We expect revenue growth of 15% for FY27.", 2),
        P("Capex", "capex", "Rs 600 crore", 600, None, "crore", 2027, None, "Ravi Shah",
          "Capex for FY27 will be Rs 600 crore.", 4),
    ],
    ("NORTHWIND", "Oct 2026"): [
        P("EBITDA margin", "ebitda_margin", "13%", 13, None, "%", 2028, None, "Ravi Shah",
          "We now expect EBITDA margin of 13% by FY28.", 2),
        P("Revenue growth", "revenue_growth", "15%", 15, None, "%", 2027, None, "Arjun Mehta",
          "We expect revenue growth of 15% for FY27.", 3),
        P("Halol plant commissioning", "capacity", "commissioned", None, None, "", 2027, 3, "Arjun Mehta",
          "The new Halol plant will be commissioned in Q3 FY27.", 3),
    ],
    ("KESTREL", "May 2026"): [
        P("EBITDA margin", "ebitda_margin", "13%", 13, None, "%", 2027, 2, "Ravi Shah",
          "For Q2 FY27 we expect EBITDA margin of 13.5%.", 2),
    ],
    ("KESTREL", "Jul 2026"): [
        P("Revenue growth", "revenue_growth", "15%", 15, None, "%", 2027, None, "Arjun Mehta",
          "We expect revenue growth of 15% for FY27.", 2),
    ],
}

SUMMARIES = {
    "nse-s1": "Q2 FY27 revenue Rs 7,450 cr, up 15% YoY; PAT Rs 712 cr, up 15%.",
    "nse-s2": "CFO Ravi Shah resigns effective 31 Dec 2026; Meera Iyer appointed CFO from 1 Jan 2027.",
    "nse-s3": "Promoter group pledged 4.2% of total shares with a lender.",
    "nse-s4": "Board approved acquisition of 100% of a Pune EV-charger maker for Rs 180 crore.",
    "nse-s5": "Board approved raising up to Rs 1,500 crore through a qualified institutional placement.",
    "nse-s6": "CARE upgraded long-term rating to AA+ from AA; outlook stable.",
    "nse-s7": "Won Rs 420 crore order for power-transmission cables from a state utility.",
    "nse-s8": "Interim dividend of Rs 6 per share; record date 24 Nov 2026.",
    "nse-s9": "Q2 FY27 PAT Rs 925 cr, up 15% YoY; NII up 12%.",
    "nse-s10": "Q2 FY27 revenue up 15% YoY; EBITDA margin 13.4%.",
    "nse-s11": "Received GST demand of Rs 38 crore for FY22; company plans to appeal.",
    "nse-s12": "Transcript of Q2 FY27 earnings call uploaded.",
}


def fake_call(tier, prompt, *, step, system=None, schema=None, json_mode=True):
    if step == "promise_extract":
        sym = re.search(r"\(NSE: (\w+)\)", prompt).group(1)
        when = re.search(r"took place in (\w+ \d{4})", prompt).group(1)
        out = {"items": EXTRACT.get((sym, when), [])}
    elif step == "promise_verdicts" and "KESTREL" in prompt:
        out = {"verdicts": [], "summary": "Only two promises so far: the Q2 FY27 margin target was met, and FY27 growth is on track at the halfway mark."}
    elif step == "promise_verdicts":
        ids = re.findall(r"'([A-Z]+-\d+)'", prompt.split("for these ids only:")[1].split("\n")[0])
        out = {"verdicts": [{"id": i, "status": "unverifiable", "actual_text": "",
                             "reason": "Reported numbers don't show plant or capacity progress."} for i in ids],
               "summary": ("Growth promises are broadly being met: FY26 growth beat the 12% target and FY27 is running at 15%. "
                           "Margins are the weak spot: the Q2 FY27 margin target was missed, the FY28 target was cut from 14% "
                           "to 13%, and the plan to double B2C capacity has not been mentioned since January.")}
    elif step == "business_snapshot":
        out = {"what_they_do": "Makes wires and cables, plus a smaller fast moving electrical goods (FMEG) business.",
               "page": 2, "segments": [{"name": "Wires and cables", "detail": "About 88% of revenue; grew 16% this quarter", "page": 2},
                                        {"name": "FMEG", "detail": "About 10% of revenue; grew 9% this quarter", "page": 2}],
               "revenue_mix": "Wires and cables 88%, FMEG 10%", "mix_page": 2}
    elif step == "bull_bear":
        pil = re.findall(r"^- ([a-z]+-[a-z]+):", prompt, re.M)
        out = {"bull": [{"text": "Revenue has compounded at about 21% a year for three years with stable 13% margins.", "source": "reported numbers"},
                        {"text": "FY26 growth beat management's own 12% target.", "source": "Q3 FY26 call p.2"},
                        {"text": "Cash from operations covered 84% of profit over five years.", "source": "reported numbers"}],
               "bear": [{"text": "Management cut its FY28 margin target from 14% to 13% within three calls.", "source": "Q2 FY27 call p.2"},
                        {"text": "FMEG competition is rising and the company chose to hold prices.", "source": "Q2 FY27 call p.3"},
                        {"text": "Cash conversion cycle stretched from 78 to 84 days.", "source": "reported numbers"}],
               "pillars": [{"pillar_id": p, "bear": {"nw-growth": "H1 FY27 growth is 15.1%, right at the line; one weak quarter breaks it.",
                                                     "nw-margin": "Margin has been 13-14% for 6 quarters and management now guides 13% for FY28.",
                                                     "nw-pledge": "No pledging is visible in the material; no real bear case.",
                                                     "ks-cash": "Working capital needs rise with growth in contract manufacturing."}.get(p, "No bear case in the material."),
                            "would_prove_wrong": {"nw-margin": "Two quarters above 14% EBITDA margin."}.get(p, "Next two quarters of reported numbers."),
                            "source": "Q2 FY27 call p.2", "supported": p != "nw-pledge"} for p in pil]}
    elif step == "summaries":
        ids = re.findall(r"### id=(\S+)", prompt)
        out = {"items": [{"id": i, "summary": SUMMARIES.get(i, "Filing summary.")} for i in ids]}
    elif step == "mgmt_change":
        out = {"people": [
            {"name": "Ravi Shah", "role": "Chief Financial Officer", "change": "leaving", "effective_date": "31 Dec 2026", "profile_summary": None},
            {"name": "Meera Iyer", "role": "Chief Financial Officer", "change": "joining", "effective_date": "1 Jan 2027",
             "profile_summary": "Chartered accountant with 22 years in finance. Previously CFO of a listed auto-components maker for 6 years; "
                                "before that, treasury roles at two cable and power companies."}]}
    elif step == "results_pdf":
        out = {"found": False}
    else:
        out = {"items": []}
    text = json.dumps(out)
    spec = llm._cfg()["strong" if tier == "strong" else "cheap"]
    tin, tout = len(prompt) // 4, len(text) // 4
    llm._log_cost({"ts": common.iso(NOW), "step": step, "tier": tier, "model": spec["model"], "in_tok": tin, "out_tok": tout,
                   "inr": round(tin / 1e6 * spec["inr_per_1m_input"] + tout / 1e6 * spec["inr_per_1m_output"], 4),
                   "cache_hit": False})
    return llm._validate(text, schema)


llm.call = fake_call
llm.cheap = lambda prompt, **kw: fake_call("cheap", prompt, **kw)
llm.strong = lambda prompt, **kw: fake_call("strong", prompt, **kw)


# ---------------------------------------------------------------- fake prices + filings

def sessions(n=30):
    d, out = NOW.date(), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def make_prices():
    days = sessions(60)
    rnd = random.Random(7)
    stocks = {}
    special = {"NORTHWIND": (-2, -5.2, 3.1), "SUMMIT": (-1, 6.8, 2.6), "KESTREL": (-1, 2.1, 2.3)}
    for i, sym in enumerate(COMPANIES):
        price, rows = 500 + 300 * i, []
        for j, d in enumerate(days):
            chg = rnd.gauss(0.05, 1.2)
            vol = 1_000_000 * (1 + i * 0.3) * rnd.uniform(0.7, 1.3)
            sp = special.get(sym)
            if sp and j == len(days) + sp[0]:
                chg, vol = sp[1], vol * sp[2]
            price *= 1 + chg / 100
            rows.append({"Close": price, "Volume": vol})
        df = pd.DataFrame(rows, index=pd.to_datetime(days))
        series = prices.metrics_from_frame(df)
        ov = PORTFOLIO["alerts"]["overrides"].get(sym, {})
        stocks[sym] = {"symbol": sym, "yahoo": sym + ".NS", "series": series, "last": series[-1],
                       "default_breaches": prices.breaches(series, 2.0, ov.get("move_pct", 4.0))}
    write_json(DATA / "prices.json", {"as_of": common.iso(NOW), "stocks": stocks, "failed": []})
    return days


def make_filings(days):
    last = days[-1]
    def at(day_offset, hour):
        d = days[len(days) + day_offset]
        return common.iso(datetime(d.year, d.month, d.day, hour, 15, tzinfo=IST))
    F = [
        ("nse-s1", "NORTHWIND", at(-2, 17), "Outcome of Board Meeting", "Outcome of Board Meeting - approved unaudited financial results for the quarter ended September 30, 2026"),
        ("nse-s2", "NORTHWIND", at(-1, 19), "Change in Management", "Resignation of Mr. Ravi Shah as Chief Financial Officer and appointment of Ms. Meera Iyer as Chief Financial Officer"),
        ("nse-s3", "TALLGRASS", at(-1, 20), "Disclosure under SEBI Takeover Regulations", "Disclosure under Regulation 31 - creation of pledge on shares by promoter group"),
        ("nse-s4", "IRONBRIDGE", at(-3, 18), "Acquisition", "Acquisition of 100% stake in a Pune based EV charger maker for Rs 180 crore"),
        ("nse-s5", "BLUEPEAK", at(-4, 21), "Outcome of Board Meeting", "Board approved fund raising up to Rs 1,500 crore through Qualified Institutional Placement"),
        ("nse-s6", "HARBOUR", at(-5, 12), "Credit Rating", "CARE Ratings has upgraded the long term rating to AA+"),
        ("nse-s7", "IRONBRIDGE", at(-1, 11), "Press Release", "Company bags order worth Rs 420 crore for power transmission cables"),
        ("nse-s8", "ORBIT", at(-6, 18), "Dividend", "Declaration of interim dividend of Rs 6 per share"),
        ("nse-s9", "HARBOUR", at(-7, 17), "Integrated Filing- Financial", "Integrated filing - financial results for quarter ended September 30, 2026"),
        ("nse-s10", "KESTREL", at(-8, 18), "Outcome of Board Meeting", "Outcome of Board Meeting - financial results for the quarter ended September 30, 2026"),
        ("nse-s11", "SUMMIT", at(-9, 16), "Updates", "Receipt of GST demand order of Rs 38 crore for FY22"),
        ("nse-s12", "NORTHWIND", at(-1, 9), "Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of earnings call for Q2 FY27"),
    ]
    routine = [
        ("Copy of Newspaper Publication", "Newspaper publication of financial results"),
        ("Trading Window", "Closure of trading window"),
        ("Certificate under SEBI (Depositories and Participants) Regulations, 2018", "Certificate under Regulation 74(5)"),
        ("ESOP/ESOS/ESPS", "Allotment of equity shares under ESOP scheme"),
        ("Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of analyst / institutional investor meetings"),
        ("Board Meeting Intimation", "Intimation of board meeting to consider financial results"),
        ("Shareholders meeting", "Notice of postal ballot"),
        ("Investor Presentation", "Investor presentation for Q2 FY27"),
        ("Loss of Share Certificates", "Loss of share certificate"),
        ("Analysts/Institutional Investor Meet/Con. Call Updates", "Audio recording of earnings call"),
    ]
    rnd = random.Random(3)
    syms = list(COMPANIES)
    for i in range(26):
        cat, sub = routine[i % len(routine)]
        F.append((f"nse-r{i}", syms[i % len(syms)], at(-1 - (i % 10), 9 + i % 9), cat, sub))
    items = [{"id": i, "symbol": s, "company": COMPANIES[s]["name"], "time": t, "exchange_category": c,
              "subject": sub, "url": f"https://example.com/sample/{i}.pdf", "source": "nse"} for i, s, t, c, sub in F]
    items.sort(key=lambda x: x["time"], reverse=True)
    write_json(DATA / "announcements.json", {"as_of": common.iso(NOW), "items": items, "report": {}})


classify._excerpt = lambda item, s: ("Brief profile of Ms. Meera Iyer: chartered accountant ..." if item["id"] == "nse-s2" else "")


def main():
    days = make_prices()
    fundamentals.run(list(COMPANIES))
    make_filings(days)
    classify.run()
    for sym in PORTFOLIO["research"]:
        r = research.build(sym, progress=lambda m: None, refresh=True)
        promises.print_ledger(r["ledger"])
    write_json(WEB_DATA / "nse_symbols.json", [{"s": s, "n": c["name"]} for s, c in COMPANIES.items()])
    meta = build_digest.run(sample=True)
    print("sample snapshot written:", WEB_DATA, "| cost", meta["cost"]["total"])


if __name__ == "__main__":
    main()

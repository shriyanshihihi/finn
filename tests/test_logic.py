"""Offline tests: parsing and ledger logic, no network and no model calls."""
from pathlib import Path

from pipeline.common import qindex, quarter_discussed_on_call, quarter_of_period_end
from pipeline.fundamentals import parse
from pipeline.promises import link, settle_in_code, display_status, quote_found

FIX = Path(__file__).parent / "fixtures"


def fixture_company():
    return parse((FIX / "screener_sample.html").read_text(), "SAMPLECAB", "consolidated", "u")


def item(metric, key, low, fy, q, said_fy, said_q, quote="x", high=None, speaker="Ravi Shah"):
    return {"metric": metric, "metric_key": key, "target_text": f"{low}", "target_low": low, "target_high": high,
            "unit": "%", "deadline_text": "", "deadline_fy": fy, "deadline_q": q, "speaker_name": speaker,
            "speaker_role": "CFO", "verbatim_quote": quote, "page": 3, "quarter_said": f"Q{said_q} FY{said_fy % 100}",
            "qidx_said": qindex(said_fy, said_q), "call_date": "", "transcript_url": "u"}


def test_fiscal_calendar():
    assert quarter_of_period_end(9, 2026) == (2027, 2)
    assert quarter_of_period_end(3, 2026) == (2026, 4)
    assert quarter_discussed_on_call(11, 2026) == (2027, 2)
    assert quarter_discussed_on_call(1, 2027) == (2027, 3)
    assert quarter_discussed_on_call(5, 2026) == (2026, 4)


def test_ledger_statuses():
    f = fixture_company()
    calls = [qindex(2026, 3), qindex(2026, 4), qindex(2027, 1), qindex(2027, 2)]
    items = [
        # Q2 FY27 margin target 13.5 -> actual 1000/7450 = 13.4 -> missed
        item("EBITDA margin", "ebitda_margin", 13.5, 2027, 2, 2026, 4),
        # FY26 revenue growth >= 12 -> 25369 vs 22408 = 13.2% -> kept
        item("Revenue growth", "revenue_growth", 12, 2026, None, 2026, 3),
        # revised: FY28 margin 14 then 13
        item("FY28 margin", "ebitda_margin", 14, 2028, None, 2026, 4),
        item("FY28 margin", "ebitda_margin", 13, 2028, None, 2027, 2),
        # quietly dropped: said only in Q3 FY26 about FY28 capacity, never again
        item("Double B2C capacity", "capacity", 2, 2028, None, 2026, 3),
        # pending full-year growth with progress
        item("Revenue growth", "revenue_growth", 15, 2027, None, 2027, 1),
    ]
    th = link(items, calls, "SAMPLECAB")
    settle_in_code(th, f)
    by = {t["metric"]: t for t in th}
    assert by["EBITDA margin"]["status"] == "missed", by["EBITDA margin"]
    assert by["Revenue growth"]["status"] in ("kept", "pending")
    fy26 = [t for t in th if t["metric"] == "Revenue growth" and t["deadline_fy"] == 2026][0]
    assert fy26["status"] == "kept", fy26
    fy28 = by["FY28 margin"]
    assert fy28["revised"] and fy28["revision_direction"] == "down" and fy28["times_said"] == 2
    assert by["Double B2C capacity"]["quietly_dropped"]
    pend = [t for t in th if t["metric"] == "Revenue growth" and t["deadline_fy"] == 2027][0]
    assert pend["status"] == "pending" and pend["progress"].startswith("H1 FY27"), pend
    for t in th:
        t["display_status"] = display_status(t)
    assert fy28["display_status"] == "revised"
    assert by["Double B2C capacity"]["display_status"] == "dropped"


def test_quote_check():
    pages = ["intro", "Ravi Shah: We are targeting 14% EBITDA\nmargin by FY28. Thank you.", "end"]
    assert quote_found("We are targeting 14% EBITDA margin by FY28.", pages, 2) == 2
    assert quote_found("We are targeting 14% EBITDA margin by FY28.", pages, 3) == 2
    assert quote_found("We will triple revenue next year.", pages, 2) is None


def test_filing_rules_on_real_exchange_wording():
    from pipeline.classify import Rules

    r = Rules()
    kmp = "Change in Directors/ Key Managerial Personnel/ Auditor/ Compliance Officer/ Share Transfer Agent"
    cases = [
        # NSE's catch-all label must not make a CFO exit look routine
        ({"exchange_category": kmp, "subject": "ACME Ltd has informed the Exchange about resignation of Mr. A Rao, Chief Financial Officer"},
         ("management_change", True)),
        ({"exchange_category": kmp, "subject": "ACME Ltd has informed the Exchange about appointment of Ms. B Iyer as Company Secretary"},
         ("management_change", False)),
        ({"exchange_category": kmp, "subject": "ACME Ltd has informed the Exchange about appointment of M/s XYZ & Co as Statutory Auditor"},
         ("unclassified", False)),
        ({"exchange_category": "Board Meeting Intimation",
          "subject": "ACME Ltd has informed the Exchange about Board Meeting to be held on 12-Nov-2026 to consider unaudited financial results"},
         ("results", False)),
        ({"exchange_category": "Financial Result Updates", "subject": "ACME Ltd has submitted unaudited financial results for the quarter ended September 30, 2026"},
         ("results", True)),
        ({"exchange_category": "Analysts/Institutional Investor Meet/Con. Call Updates",
          "subject": "ACME Ltd has informed the Exchange about Transcript of the earnings call held on 13-Nov-2026"},
         ("earnings_call", True)),
        ({"exchange_category": "Analysts/Institutional Investor Meet/Con. Call Updates",
          "subject": "ACME Ltd has informed the Exchange about schedule of meeting with institutional investors"},
         ("investor_meetings", False)),
        ({"exchange_category": "Credit Rating", "subject": "CRISIL has reaffirmed the rating of ACME Ltd at AA+/Stable"},
         ("credit_rating", False)),
        ({"exchange_category": "Credit Rating", "subject": "ICRA has upgraded the long-term rating to AA+"},
         ("credit_rating", True)),
        ({"exchange_category": "Updates", "subject": "ACME Ltd has received an order worth Rs 1,250 crore from NHAI"},
         ("press_release", True)),
        ({"exchange_category": "Updates", "subject": "ACME Ltd launches new product range"},
         ("press_release", False)),
        ({"exchange_category": "Copy of Newspaper Publication", "subject": "Newspaper publication of financial results"},
         ("unclassified", False)),
        ({"exchange_category": "Disclosure under SEBI Takeover Regulations", "subject": "Disclosure of encumbrance of shares by promoter"},
         ("pledging", True)),
    ]
    for item, want in cases:
        got = r.match(item)
        assert got is not None and got[:2] == want, (item["subject"], got)

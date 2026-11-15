"""Management-change cards.

For a management_change filing we want three things:
  - who is leaving and who is joining (cheap model reads the filing)
  - a short background of the person joining. Appointment filings usually carry a
    "brief profile" already, so we use that first. Only if it's missing do we search
    the web (Tavily, optional key) for public professional background.
  - "orphaned promises": open guidance that the person LEAVING gave on earnings calls.
    If the CFO who promised 14% margins is leaving, that promise has lost its owner.
"""
from __future__ import annotations

import os
import re
from typing import Literal, Optional

import requests
from pydantic import BaseModel
from rapidfuzz import fuzz

from . import llm
from .common import DATA, read_json


class Person(BaseModel):
    name: str
    role: str
    change: Literal["joining", "leaving", "other"]
    effective_date: Optional[str] = None
    profile_summary: Optional[str] = None


class People(BaseModel):
    people: list[Person]


def _clean(name: str) -> str:
    return re.sub(r"^(mr|ms|mrs|dr|shri|smt)\.?\s+", "", name.strip(), flags=re.I)


def read_filing(symbol: str, subject: str, excerpt: str) -> list[dict]:
    text = excerpt or subject
    prompt = (
        f"This is a management-change filing by {symbol} on an Indian stock exchange.\n"
        "List each person whose position changes: name, role (e.g. Chief Financial Officer), "
        "change = joining / leaving / other, effective_date if stated.\n"
        "For a person joining, profile_summary = their background in at most 3 short lines, "
        "ONLY from a profile given in this text (past employers, roles, qualifications). "
        "If the text has no profile, profile_summary = null.\n"
        'Return JSON: {"people": [{"name", "role", "change", "effective_date", "profile_summary"}]}\n\n'
        f"Subject: {subject}\n\n{text[:8000]}"
    )
    try:
        return llm.cheap(prompt, step="mgmt_change", schema=People)["people"]
    except (llm.LLMUnavailable, llm.LLMError):
        return []


class Bio(BaseModel):
    summary: Optional[str] = None


def search_bio(name: str, role: str, company: str) -> dict | None:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return None
    try:
        r = requests.post("https://api.tavily.com/search", timeout=30, json={
            "api_key": key, "query": f'"{name}" {role} career background', "max_results": 5})
        r.raise_for_status()
        results = r.json().get("results", [])
    except requests.RequestException:
        return None
    if not results:
        return None
    blocks = "\n\n".join(f"[{i}] {x['title']} ({x['url']})\n{x.get('content', '')[:800]}" for i, x in enumerate(results))
    prompt = (
        f"{name} is joining {company} as {role}. From the search results below ONLY, write their professional "
        "background in at most 3 short lines (past employers, roles, years if given). If the results are about a "
        'different person or say nothing useful, return {"summary": null}.\nReturn JSON: {"summary": ...}\n\n' + blocks
    )
    try:
        s = llm.cheap(prompt, step="bio_search", schema=Bio)["summary"]
    except (llm.LLMUnavailable, llm.LLMError):
        return None
    if not s:
        return None
    return {"text": s, "source": "web", "links": [{"title": x["title"], "url": x["url"]} for x in results[:3]]}


def orphaned(symbol: str, leaver: str) -> list[dict]:
    L = read_json(DATA / "promises" / f"{symbol}.json")
    if not L:
        return []
    who = _clean(leaver).lower()
    out = []
    for t in L["threads"]:
        if t["display_status"] in ("kept", "missed"):
            continue
        if any(fuzz.token_set_ratio(who, _clean(s).lower()) >= 85 for s in t["speakers"]):
            m = t["mentions"][-1]
            out.append({"id": t["id"], "metric": t["metric"], "target": t["target_text"], "deadline": t["deadline"],
                        "quote": m["verbatim_quote"], "page": m["page"], "transcript_url": m["transcript_url"],
                        "said": m["quarter_said"]})
    return out


def management_card(item: dict, company: str) -> dict:
    people = read_filing(item["symbol"], item["subject"], item.get("excerpt", ""))
    out = []
    for p in people:
        entry = dict(p)
        if p["change"] == "joining":
            if p.get("profile_summary"):
                entry["bio"] = {"text": p["profile_summary"], "source": "filing", "links": []}
            else:
                entry["bio"] = search_bio(p["name"], p["role"], company)
        if p["change"] == "leaving":
            entry["orphaned_promises"] = orphaned(item["symbol"], p["name"])
        out.append(entry)
    return {"people": out, "has_ledger": (DATA / "promises" / f"{item['symbol']}.json").exists()}

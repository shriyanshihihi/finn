"""Read a concall transcript PDF and split it into speaker turns.

Indian concall transcripts follow a common layout:
  page 1: company, call date, "MANAGEMENT: MR. A - CFO ..." block
  then:   "Moderator: ...", "Name: ...", "The next question is from the line of X from Y"

We label every turn as management / analyst / moderator, so that only what
management actually said is ever treated as a promise.
"""
from __future__ import annotations

import re

from .pdftext import pages, readable

TURN = re.compile(
    r"^\s*((?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri)?\s*[A-Z][A-Za-z.'\-]*(?:\s+[A-Z][A-Za-z.'\-]*){0,4})\s*[:：]\s*(.*)$"
)
NOT_NAMES = {"note", "disclaimer", "page", "safe harbor", "safe harbour", "q", "a", "date", "time",
             "management", "moderator", "participants", "analyst", "analysts", "speakers", "host",
             "corporate participants", "conference call participants", "email", "website", "cin", "tel"}
INTRO = re.compile(
    r"(?:question (?:is |comes )?from|line of|we have)\s+(?:the line of\s+)?"
    r"((?:Mr\.?|Ms\.?|Dr\.?)?\s*[A-Z][a-zA-Z.'\-]*(?:\s+[A-Z][a-zA-Z.'\-]*){0,3})\s+(?:from|with)\s",
)
FORWARD = re.compile(
    r"\b(guid|expect|target|aim|outlook|anticipat|plan to|will be|should be|going forward|"
    r"next (?:year|quarter|fiscal)|by fy|fy ?\d{2}|run[- ]rate|bps|basis points|capex|capacity|"
    r"utili[sz]ation|margin|crore|cr\b|%|percent|double|cagr|breakeven|commission)", re.I)


def _norm(name: str) -> str:
    n = re.sub(r"^(mr|ms|mrs|dr|shri)\.?\s+", "", name.strip(), flags=re.I)
    return re.sub(r"\s+", " ", n).strip().lower()


def _same_person(a: str, b: str) -> bool:
    ta, tb = set(_norm(a).split()), set(_norm(b).split())
    if not ta or not tb:
        return False
    common = ta & tb
    return bool(common) and (len(common) >= min(len(ta), len(tb), 2) or len(common) == min(len(ta), len(tb)))


def participants(first_pages: str) -> list[dict]:
    """Names + roles from the 'MANAGEMENT:' block on page 1-2."""
    text = first_pages.replace("–", "-").replace("—", "-")
    m = re.search(r"MANAGEMENT\s*:?(.{0,2500}?)(?:MODERATOR|Moderator\s*:|ANALYST|$)", text, re.S)
    if not m:
        return []
    block = m.group(1)
    out = []
    for nm, role in re.findall(r"(?:MR|MS|MRS|DR|SHRI)\.?\s+([A-Z][A-Za-z.\s]{2,40}?)\s*[-,]\s*([^\n]{2,90})", block, re.I):
        out.append({"name": re.sub(r"\s+", " ", nm).strip().title(), "role": role.strip(" ,.-").title()})
    return out


def parse(page_texts: list[str]) -> dict:
    head = "\n".join(page_texts[:2])
    people = participants(head)
    turns: list[dict] = []
    analysts: set[str] = set()
    current = None
    pending_intro = False
    for pi, txt in enumerate(page_texts, start=1):
        for line in txt.splitlines():
            m = TURN.match(line)
            name = m.group(1).strip() if m else ""
            is_mod = bool(m) and _norm(name) in ("moderator", "operator")
            if m and len(name) <= 45 and (is_mod or _norm(name) not in NOT_NAMES) and not line.strip().isupper():
                current = {"speaker": "Moderator" if is_mod else name, "page": pi, "text": m.group(2).strip(), "pages": [pi]}
                if pending_intro and not is_mod:
                    analysts.add(_norm(name))
                    pending_intro = False
                turns.append(current)
            elif current is not None:
                current["text"] += " " + line.strip()
                if pi not in current["pages"]:
                    current["pages"].append(pi)
        # moderator introductions -> analyst names
    for t in turns:
        if t["speaker"] == "Moderator":
            for nm in INTRO.findall(t["text"]):
                analysts.add(_norm(nm))
    # second pass: label roles
    seen_first_question = False
    for i, t in enumerate(turns):
        if t["speaker"] == "Moderator":
            t["role"] = "moderator"
            if INTRO.search(t["text"]) or "first question" in t["text"].lower():
                seen_first_question = True
            continue
        mgmt = next((p for p in people if _same_person(p["name"], t["speaker"])), None)
        if mgmt:
            t["role"], t["title"] = "management", mgmt["role"]
        elif _norm(t["speaker"]) in analysts or any(_same_person(a, t["speaker"]) for a in analysts):
            t["role"] = "analyst"
        elif not seen_first_question:
            t["role"] = "management"  # opening remarks
        else:
            # follows the moderator introducing someone -> analyst; otherwise treat as management
            prev = turns[i - 1] if i else None
            t["role"] = "analyst" if prev and prev["speaker"] == "Moderator" and INTRO.search(prev["text"]) else "management"
        t.setdefault("title", "")
    return {"participants": people, "turns": turns}


def load(url: str, s=None) -> dict:
    texts = pages(url, s)
    doc = {"url": url, "pages": len(texts), "readable": readable(texts), "page_texts": texts}
    if doc["readable"]:
        doc.update(parse(texts))
    else:
        doc.update({"participants": [], "turns": []})
    return doc


def forward_looking(doc: dict) -> list[dict]:
    """Management turns that talk about the future. This is what we send to the model."""
    out = []
    for t in doc["turns"]:
        if t.get("role") != "management":
            continue
        sents = re.split(r"(?<=[.?!])\s+", t["text"])
        keep = [s for s in sents if FORWARD.search(s)]
        if keep:
            out.append({**t, "text": " ".join(keep)})
    return out


def opening_remarks(doc: dict, max_words: int = 2500) -> list[dict]:
    """Management's prepared remarks before the Q&A (used for the business snapshot)."""
    out, words = [], 0
    for t in doc["turns"]:
        if t["role"] == "analyst":
            break
        if t["role"] == "management":
            out.append(t)
            words += len(t["text"].split())
            if words > max_words:
                break
    return out


def approx_tokens(text: str) -> int:
    return len(text) // 4

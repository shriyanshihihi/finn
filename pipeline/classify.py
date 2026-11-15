"""Sort every filing into a category and decide if it's material.

1. Regex rules from config/rules.yaml (free, instant, explainable)
2. Only the leftovers go to the cheap model, all in one batched call
3. Material filings get a one-line summary (cheap model, batched), written from the
   attachment PDF when we can read it
"""
from __future__ import annotations

import random
import re
from typing import Literal

from pydantic import BaseModel

from . import llm
from .common import DATA, load_yaml, log, read_json, session, write_json
from .pdftext import pages

CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
]

Category = Literal[
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
]


class Guess(BaseModel):
    id: str
    category: Category
    confidence: float


class Guesses(BaseModel):
    items: list[Guess]


class Summary(BaseModel):
    id: str
    summary: str


class Summaries(BaseModel):
    items: list[Summary]


class Rules:
    def __init__(self):
        cfg = load_yaml("rules.yaml")
        self.rules = [(re.compile(r["match"], re.I), r["category"], r["material"], r["match"]) for r in cfg["rules"]]
        self.rewrites = [(re.compile(r["from"], re.I), r["to"]) for r in cfg.get("rewrite", [])]
        self.value = re.compile(cfg["value_pattern"], re.I)
        self.default_material = cfg["default_material"]

    def text_of(self, item: dict) -> str:
        cat = item.get("exchange_category", "") or ""
        # some exchange categories are catch-all labels that name every possibility at once;
        # swap them for a neutral word so the subject line decides
        for rx, to in self.rewrites:
            cat = rx.sub(to, cat)
        return f"{cat} | {item.get('subject', '')}".lower()

    def match(self, item: dict) -> tuple[str, bool, str] | None:
        text = self.text_of(item)
        for rx, cat, material, src in self.rules:
            if rx.search(text):
                if material == "value":
                    material = bool(self.value.search(text))
                return cat, bool(material), src
        return None


def _excerpt(item: dict, s) -> str:
    if not item.get("url") or not str(item["url"]).lower().endswith(".pdf"):
        return ""
    try:
        return "\n".join(pages(item["url"], s, max_pages=4))[:6000]
    except Exception:
        return ""


def _llm_classify(left: list[dict]) -> dict[str, tuple[str, float]]:
    if not left:
        return {}
    lines = "\n".join(f'{x["id"]}\t{x["exchange_category"]}\t{x["subject"][:220]}' for x in left)
    prompt = (
        "Classify each Indian stock-exchange filing into exactly one category.\n"
        f"Categories: {', '.join(CATEGORIES)}.\n"
        "Use 'unclassified' for routine compliance paperwork.\n"
        "Return JSON: {\"items\": [{\"id\": ..., \"category\": ..., \"confidence\": 0-1}]}\n\n"
        "id\texchange category\tsubject\n" + lines
    )
    res = llm.cheap(prompt, step="classify", schema=Guesses)
    return {g["id"]: (g["category"], g["confidence"]) for g in res["items"]}


def _llm_summaries(items: list[dict]) -> dict[str, str]:
    out = {}
    for i in range(0, len(items), 8):
        batch = items[i:i + 8]
        blocks = []
        for x in batch:
            body = x.get("excerpt") or x["subject"]
            blocks.append(f"### id={x['id']} ({x['symbol']}, {x['category']})\nSubject: {x['subject'][:300]}\n{body[:2500]}")
        prompt = (
            "Write a one-line summary for each filing below, for a busy investor.\n"
            "Rules: at most 18 words; facts and numbers only; no adjectives like 'strong' or 'robust'; "
            "use only what the text says; if the text is empty, summarise the subject.\n"
            "Return JSON: {\"items\": [{\"id\": ..., \"summary\": ...}]}\n\n" + "\n\n".join(blocks)
        )
        try:
            res = llm.cheap(prompt, step="summaries", schema=Summaries)
            out.update({s["id"]: s["summary"] for s in res["items"]})
        except (llm.LLMUnavailable, llm.LLMError) as e:
            log("classify", f"summaries skipped: {str(e)[:80]}")
            break
    return out


def run() -> dict:
    ann = read_json(DATA / "announcements.json", {"items": []})
    rules = Rules()
    items = ann["items"]
    left = []
    for it in items:
        hit = rules.match(it)
        if hit:
            it["category"], it["material"], it["rule"] = hit
            it["classified_by"] = "rule"
        else:
            left.append(it)

    guesses = {}
    try:
        guesses = _llm_classify(left)
    except (llm.LLMUnavailable, llm.LLMError) as e:
        log("classify", f"LLM pass skipped: {str(e)[:80]}")
    for it in left:
        cat, conf = guesses.get(it["id"], ("unclassified", 0.0))
        it["category"] = cat
        it["material"] = bool(rules.default_material.get(cat, False))
        it["rule"] = f"model ({conf:.2f})" if it["id"] in guesses else "no rule matched"
        it["classified_by"] = "model" if it["id"] in guesses else "fallback"

    # read attachments of material filings (needed for summaries, results, management changes)
    s = session(referer="https://www.nseindia.com/")
    material = [it for it in items if it["material"]]
    for it in material:
        it["excerpt"] = _excerpt(it, s)

    sums = _llm_summaries(material)
    for it in material:
        it["summary"] = sums.get(it["id"])

    by_rule = sum(1 for it in items if it["classified_by"] == "rule")
    stats = {"total": len(items), "by_rules": by_rule, "by_model": sum(1 for it in items if it["classified_by"] == "model"),
             "fallback": sum(1 for it in items if it["classified_by"] == "fallback"),
             "material": len(material)}
    ann["stats"] = stats
    write_json(DATA / "classified.json", ann)

    print(f"\n{stats['total']} filings: {by_rule} by rules, {stats['by_model']} by model, "
          f"{stats['fallback']} unsure, {stats['material']} material")
    for it in random.sample(items, min(10, len(items))):
        print(f"  {it['symbol']:<11}{it['category']:<18}{'M' if it['material'] else '-'}  "
              f"{it['subject'][:60]!r}  <- {it['rule'][:40]}")
    return ann


if __name__ == "__main__":
    run()

"""Model layer: two tiers (cheap / strong), a disk cache, and a cost log.

Every call goes through `call()`. It
  1. builds a cache key from model + prompt version + prompt, and returns the cached
     answer if we have one (cost 0),
  2. otherwise calls the provider, retrying on rate limits, then falling back
     to the next model in the chain,
  3. validates JSON against a pydantic schema (one retry with the error appended),
  4. appends a line to data/cost_log.jsonl.

If no API key is set, LLMUnavailable is raised and callers fall back to rules.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from typing import Any

import requests
from pydantic import BaseModel, TypeAdapter, ValidationError

from .common import CACHE, DATA, load_yaml, log, now_ist, iso

COST_LOG = DATA / "cost_log.jsonl"
_DB = CACHE / "llm.sqlite"
_lock = threading.Lock()
STATS = {"calls": 0, "cache_hits": 0, "inr": 0.0, "in_tok": 0, "out_tok": 0}


class LLMUnavailable(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


def _cfg() -> dict:
    return load_yaml("models.yaml")


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(_DB)
    con.execute("create table if not exists cache (k text primary key, v text, created text)")
    return con


def _key_for(provider: str) -> str | None:
    return {
        "gemini": os.environ.get("GEMINI_API_KEY"),
        "groq": os.environ.get("GROQ_API_KEY"),
    }.get(provider)


def available(tier: str = "cheap") -> bool:
    c = _cfg()
    chain = _chain(tier, c)
    return any(_key_for(c[t]["provider"]) for t in chain)


def _chain(tier: str, c: dict) -> list[str]:
    if tier == "strong":
        return ["strong", "cheap", "fallback"]
    return ["cheap", "fallback"]


# ---------------------------------------------------------------- providers

def _gemini(model: str, key: str, prompt: str, system: str | None, json_mode: bool) -> tuple[str, int, int]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    r = requests.post(url, json=body, timeout=180)
    if r.status_code != 200:
        raise _http_error(r)
    j = r.json()
    try:
        text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        raise LLMError(f"gemini returned no text: {str(j)[:300]}")
    u = j.get("usageMetadata", {})
    out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return text, u.get("promptTokenCount", 0), out


def _groq(model: str, key: str, prompt: str, system: str | None, json_mode: bool) -> tuple[str, int, int]:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt + ("\n\nReply with JSON only." if json_mode else "")})
    body: dict[str, Any] = {"model": model, "messages": msgs, "temperature": 0}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json=body,
        timeout=180,
    )
    if r.status_code != 200:
        raise _http_error(r)
    j = r.json()
    u = j.get("usage", {})
    return j["choices"][0]["message"]["content"], u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


class _Retryable(LLMError):
    pass


def _http_error(r: requests.Response) -> LLMError:
    msg = f"HTTP {r.status_code}: {r.text[:300]}"
    if r.status_code == 404:
        msg += "  -> model name not found; put a current model name in config/models.yaml"
    if r.status_code in (429, 500, 502, 503, 504):
        return _Retryable(msg)
    return LLMError(msg)


_PROVIDERS = {"gemini": _gemini, "groq": _groq}


# ---------------------------------------------------------------- main entry

def _strip_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t


def _validate(text: str, schema: Any) -> Any:
    obj = json.loads(_strip_fences(text))
    if schema is None:
        return obj
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_validate(obj).model_dump()
    return TypeAdapter(schema).validate_python(obj)


def _log_cost(entry: dict) -> None:
    with _lock:
        with COST_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        STATS["calls"] += 0 if entry["cache_hit"] else 1
        STATS["cache_hits"] += 1 if entry["cache_hit"] else 0
        STATS["inr"] += entry["inr"]
        STATS["in_tok"] += entry["in_tok"]
        STATS["out_tok"] += entry["out_tok"]


def call(
    tier: str,
    prompt: str,
    *,
    step: str,
    system: str | None = None,
    schema: Any = None,
    json_mode: bool = True,
) -> Any:
    c = _cfg()
    version = c.get("prompt_version", 1)
    last_err: Exception | None = None
    tried_any = False

    for slot in _chain(tier, c):
        spec = c[slot]
        provider, model = spec["provider"], spec["model"]
        key = _key_for(provider)
        if not key:
            continue
        tried_any = True
        ck = hashlib.sha256(json.dumps([provider, model, version, system, prompt]).encode()).hexdigest()

        with _lock:
            con = _db()
            row = con.execute("select v from cache where k=?", (ck,)).fetchone()
            con.close()
        if row:
            try:
                out = _validate(row[0], schema) if json_mode else row[0]
                _log_cost({"ts": iso(now_ist()), "step": step, "tier": tier, "model": model,
                           "in_tok": 0, "out_tok": 0, "inr": 0.0, "cache_hit": True})
                return out
            except (ValueError, ValidationError):
                pass  # stale cache entry: call again

        p = prompt
        for attempt in range(5):
            try:
                text, tin, tout = _PROVIDERS[provider](model, key, p, system, json_mode)
                inr = tin / 1e6 * spec.get("inr_per_1m_input", 0) + tout / 1e6 * spec.get("inr_per_1m_output", 0)
                _log_cost({"ts": iso(now_ist()), "step": step, "tier": tier, "model": model,
                           "in_tok": tin, "out_tok": tout, "inr": round(inr, 4), "cache_hit": False})
                if not json_mode:
                    out = text
                else:
                    try:
                        out = _validate(text, schema)
                    except (ValueError, ValidationError) as e:
                        if attempt >= 1:
                            raise LLMError(f"invalid JSON twice: {e}")
                        p = prompt + f"\n\nYour last answer failed validation: {str(e)[:500]}\nReturn valid JSON only."
                        continue
                with _lock:
                    con = _db()
                    con.execute("insert or replace into cache values (?,?,?)", (ck, text, iso(now_ist())))
                    con.commit()
                    con.close()
                return out
            except _Retryable as e:
                last_err = e
                wait = 2 ** (attempt + 1)
                log("llm", f"{model} busy ({str(e)[:60]}), retry in {wait}s")
                time.sleep(wait)
            except (LLMError, requests.RequestException) as e:
                last_err = e
                break
        log("llm", f"{model} failed for {step}: {str(last_err)[:120]} -> trying next model")

    if not tried_any:
        raise LLMUnavailable("no API key set (GEMINI_API_KEY or GROQ_API_KEY in .env)")
    raise LLMError(f"all models failed for {step}: {last_err}")


def cheap(prompt: str, **kw: Any) -> Any:
    return call("cheap", prompt, **kw)


def strong(prompt: str, **kw: Any) -> Any:
    return call("strong", prompt, **kw)


def cost_summary() -> dict:
    """Totals from the whole cost log, grouped by step."""
    by_step: dict[str, dict] = {}
    total = {"calls": 0, "cache_hits": 0, "inr": 0.0, "in_tok": 0, "out_tok": 0}
    if COST_LOG.exists():
        for line in COST_LOG.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            s = by_step.setdefault(e["step"], {"calls": 0, "cache_hits": 0, "inr": 0.0, "tokens": 0, "model": e["model"]})
            if e["cache_hit"]:
                s["cache_hits"] += 1
                total["cache_hits"] += 1
            else:
                s["calls"] += 1
                total["calls"] += 1
            s["inr"] += e["inr"]
            s["tokens"] += e["in_tok"] + e["out_tok"]
            total["inr"] += e["inr"]
            total["in_tok"] += e["in_tok"]
            total["out_tok"] += e["out_tok"]
    for s in by_step.values():
        s["inr"] = round(s["inr"], 2)
    total["inr"] = round(total["inr"], 2)
    return {"total": total, "by_step": by_step}

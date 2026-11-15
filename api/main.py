"""Live research API. The app works without it; it's only needed for tickers
that weren't precomputed.

GET  /health
GET  /company/{symbol}            cached research, if we have it
GET  /research/{symbol}/stream    run research live, progress as Server-Sent Events

Run locally:  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from pipeline import research
from pipeline.common import DATA, WEB_DATA, read_json

app = FastAPI(title="FINN research API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
_symbols: set[str] | None = None


def known(sym: str) -> bool:
    global _symbols
    if _symbols is None:
        rows = read_json(WEB_DATA / "nse_symbols.json", [])
        _symbols = {r["s"] for r in rows} if len(rows) > 100 else set()
    return sym in _symbols if _symbols else bool(SYMBOL.match(sym))


def cached(sym: str) -> dict | None:
    for base in (DATA / "companies", WEB_DATA / "companies"):
        p = base / f"{sym}.json"
        if p.exists():
            return read_json(p)
    return None


class Job:
    def __init__(self, sym: str):
        self.sym = sym
        self.events: list[dict] = []
        self.done = False
        self.started = time.time()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            research.build(self.sym, progress=lambda m: self.events.append({"type": "progress", "msg": m}))
            self.events.append({"type": "done", "symbol": self.sym})
        except Exception as e:  # report every failure to the app in one line
            self.events.append({"type": "error", "msg": _friendly(e)})
        self.done = True


def _friendly(e: Exception) -> str:
    t = str(e)
    if "not found on screener" in t:
        return "screener.in has no page for this symbol."
    if "403" in t or "429" in t:
        return "A data source blocked this server just now. Try one of the ready companies."
    if "no API key" in t:
        return "The research server has no model key set."
    return f"Research failed: {t[:140]}"


JOBS: dict[str, Job] = {}
_lock = threading.Lock()


@app.get("/health")
def health():
    meta = read_json(WEB_DATA / "meta.json", {})
    return {"ok": True, "snapshot_as_of": meta.get("as_of")}


@app.get("/company/{symbol}")
def company(symbol: str):
    sym = symbol.upper()
    c = cached(sym)
    if not c:
        raise HTTPException(404, "not researched yet")
    return JSONResponse(c)


@app.get("/research/{symbol}/stream")
async def stream(symbol: str):
    sym = symbol.upper().strip()
    if not known(sym):
        raise HTTPException(400, f"{sym} is not an NSE equity symbol")

    async def events():
        if cached(sym):
            yield _sse({"type": "done", "symbol": sym, "cached": True})
            return
        with _lock:
            job = JOBS.get(sym)
            if job is None or (job.done and time.time() - job.started > 600):
                job = JOBS[sym] = Job(sym)  # a second request for the same symbol joins the first
        sent, last_beat = 0, time.time()
        while True:
            while sent < len(job.events):
                ev = job.events[sent]
                sent += 1
                yield _sse(ev)
                if ev["type"] in ("done", "error"):
                    return
            if time.time() - last_beat > 15:
                yield ": keep-alive\n\n"
                last_beat = time.time()
            await asyncio.sleep(0.4)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(ev: dict) -> str:
    return f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"

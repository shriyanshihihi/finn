"""Small shared helpers: paths, time, config, json io, http session."""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = Path(os.environ.get("FINN_DATA", ROOT / "data"))
RAW = DATA / "raw"
CACHE = DATA / "cache"
WEB_DATA = Path(os.environ.get("FINN_WEB_DATA", ROOT / "web" / "public" / "data"))

IST = timezone(timedelta(hours=5, minutes=30))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

for d in (DATA, RAW, CACHE):
    d.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """Read .env without needing python-dotenv installed."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


def now_ist() -> datetime:
    return datetime.now(IST)


def iso(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat(timespec="seconds")


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text())


def portfolio() -> dict:
    return load_yaml("portfolio.yaml")


def holding_symbols() -> list[str]:
    return [h["symbol"] for h in portfolio()["holdings"]]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
    tmp.replace(path)


def session(referer: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    if referer:
        s.headers["Referer"] = referer
    return s


def polite(lo: float = 1.0, hi: float = 2.0) -> None:
    time.sleep(random.uniform(lo, hi))


def log(step: str, msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step:<13} {msg}", flush=True)


# ---------------------------------------------------------------- fiscal calendar
# Indian companies use April-March years. FY27 = Apr 2026 - Mar 2027.
# Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar.

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def quarter_of_period_end(month: int, year: int) -> tuple[int, int]:
    """Quarter that ENDS in this month, e.g. Sep 2026 -> (2027, 2) meaning Q2 FY27."""
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(month)
    if q is None:
        # not a quarter end month: use the quarter containing it
        q = {4: 1, 5: 1, 7: 2, 8: 2, 10: 3, 11: 3, 1: 4, 2: 4}[month]
    fy = year if q == 4 else year + 1
    return fy, q


def quarter_discussed_on_call(month: int, year: int) -> tuple[int, int]:
    """A results call in this month discusses which quarter? Nov 2026 -> Q2 FY27."""
    if month in (7, 8, 9):
        return year + 1, 1
    if month in (10, 11, 12):
        return year + 1, 2
    if month in (1, 2, 3):
        return year, 3
    return year, 4  # Apr, May, Jun


def qlabel(fy: int, q: int | None = None) -> str:
    return f"Q{q} FY{fy % 100:02d}" if q else f"FY{fy % 100:02d}"


def qindex(fy: int, q: int) -> int:
    """Monotonic number for comparing quarters."""
    return fy * 4 + (q - 1)


def parse_month_year(text: str) -> tuple[int, int] | None:
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*'?(\d{2,4})", text or "")
    if not m:
        return None
    month = MONTHS.index(m.group(1)) + 1
    y = int(m.group(2))
    if y < 100:
        y += 2000
    return month, y


def to_number(text: Any) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).replace(",", "").replace("%", "").replace("₹", "").strip()
    if t in ("", "-", "--", "NA", "N/A"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / abs(old) * 100, 1)

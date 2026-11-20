"""共用：路徑、時間、HTTP、JSON 讀寫。"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DIRS = {d: os.path.join(ROOT, d) for d in
        ("blind", "fair", "board", "evidence", "tickets", "journal")}
TPE = timezone(timedelta(hours=8))
UNAVAILABLE = "unavailable"

_S = requests.Session()
_S.headers["User-Agent"] = "polydesk-sim/0.1 (simulation only)"
_S.headers["Accept-Encoding"] = "gzip"


def now_utc():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_tpe(dt):
    return dt.astimezone(TPE).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def stamp(dt=None):
    """時間戳：同時記 UTC 與台北。"""
    dt = dt or now_utc()
    return {"utc": iso_utc(dt), "taipei": iso_tpe(dt), "epoch": dt.timestamp()}


def parse_iso(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def today_tpe(dt=None):
    return (dt or now_utc()).astimezone(TPE).strftime("%Y-%m-%d")


def http_json(method, url, retries=3, **kw):
    kw.setdefault("timeout", 30)
    last = None
    for i in range(retries):
        try:
            r = _S.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(1.5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = str(e)
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status and status < 500 and status != 429:
                break
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{method} {url} failed: {last}")


def get_json(url, **kw):
    return http_json("GET", url, **kw)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

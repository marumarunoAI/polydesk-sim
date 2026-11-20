"""quant.py — 盲算公平機率。只讀 blind/（規則）與免費標的資料（Binance K 線、
Deribit 隱含波動率、Fed 會議日程），絕不讀 board/ 或 evidence/。

觸價（reach）：touch ≈ 2·N(−|ln(X/S)|/(σ√T))
同日 above：N(d2)，d2 = (ln(S/X) − σ²T/2)/(σ√T)
σ：Binance 1h K 線 30 天實現波動率；窗口內有 FOMC 決議日 → 改用 Deribit DVOL。"""
import math
import os
import re
from statistics import pstdev

from blind import load_blind
from common import (DIRS, UNAVAILABLE, get_json, now_utc, parse_iso, read_json,
                    stamp, today_tpe, write_json)

BINANCE = "https://data-api.binance.vision/api/v3"  # 公開行情鏡像（api.binance.com 在本機被地區限制）
DERIBIT = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
SYMBOL = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
YEAR = 365 * 24 * 3600


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def touch_prob(S, X, sigma, T, direction):
    if (direction == "up" and S >= X) or (direction == "down" and S <= X):
        return 1.0
    if T <= 0 or sigma <= 0:
        return 0.0
    return min(1.0, 2 * ncdf(-abs(math.log(X / S)) / (sigma * math.sqrt(T))))


def above_prob(S, X, sigma, T):
    if T <= 0 or sigma <= 0:
        return 1.0 if S > X else 0.0
    d2 = (math.log(S / X) - sigma ** 2 * T / 2) / (sigma * math.sqrt(T))
    return ncdf(d2)


def klines(asset, interval, limit):
    rows = get_json(f"{BINANCE}/klines",
                    params={"symbol": SYMBOL[asset], "interval": interval, "limit": limit})
    return [(r[0], float(r[2]), float(r[3]), float(r[4])) for r in rows]  # t, high, low, close


def market_inputs(asset):
    """回傳 spot、實現波動率、日 K（給基準率）及來源。"""
    h = klines(asset, "1h", 720)
    rets = [math.log(h[i][3] / h[i - 1][3]) for i in range(1, len(h))]
    rv = pstdev(rets) * math.sqrt(24 * 365)
    spot = float(get_json(f"{BINANCE}/ticker/price", params={"symbol": SYMBOL[asset]})["price"])
    daily = klines(asset, "1d", 1000)
    return {"spot": spot, "realized_vol": rv, "daily": daily,
            "source": f"{BINANCE}/klines?symbol={SYMBOL[asset]} (1h×720, 1d×1000) + ticker/price",
            "ts": stamp()}


def deribit_iv(asset):
    end = int(now_utc().timestamp() * 1000)
    d = get_json(DERIBIT, params={"currency": asset, "resolution": 3600,
                                  "start_timestamp": end - 6 * 3600 * 1000,
                                  "end_timestamp": end})
    data = d["result"]["data"]
    return data[-1][4] / 100.0


def fomc_decision_days():
    """Fed 官網 FOMC 日程 → 決議日（每次會議的最後一天）UTC 日期字串清單。"""
    from common import _S
    html = _S.get(FOMC_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text
    out = []
    for year in re.findall(r"(\d{4}) FOMC Meetings", html):
        i = html.find(f"{year} FOMC Meetings")
        j = html.find("FOMC Meetings", i + 20)
        seg = html[i:j if j > 0 else None]
        for mon, days in re.findall(
                r'fomc-meeting__month[^>]*>\s*<strong>([A-Za-z/]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<',
                seg, re.S):
            last = re.findall(r"\d+", days)
            if not last:
                continue
            mon = mon.split("/")[-1] if "-" in days and "/" in mon else mon.split("/")[0]
            try:
                from datetime import datetime
                d = datetime.strptime(f"{year} {mon[:3]} {last[-1]}", "%Y %b %d")
                out.append(d.strftime("%Y-%m-%d"))
            except ValueError:
                continue
    return sorted(set(out))


def base_rate(daily, S, X, days, kind, direction):
    """歷史基準率：過去日 K 中，n 天內移動到同樣比例的頻率。"""
    n = max(1, math.ceil(days))
    ratio = X / S
    hits = total = 0
    for i in range(1, len(daily) - n + 1):
        s0 = daily[i - 1][3]
        win = daily[i:i + n]
        if kind == "reach":
            ok = (max(w[1] for w in win) / s0 >= ratio) if direction == "up" \
                else (min(w[2] for w in win) / s0 <= ratio)
        else:
            ok = win[-1][3] / s0 > ratio
        hits += ok
        total += 1
    return (round(hits / total, 4), total) if total >= 30 else (UNAVAILABLE, total)


def price_one(b, inp, iv, fomc, now):
    end = parse_iso(b["end_utc"])
    T = max(0.0, (end - now).total_seconds() / YEAR)
    sigma, src = inp["realized_vol"], "binance_realized_1h_30d"
    event = UNAVAILABLE if fomc is None else any(
        now.strftime("%Y-%m-%d") <= d <= end.strftime("%Y-%m-%d") for d in fomc)
    if event is True:
        if iv is None:
            sigma, src = UNAVAILABLE, "deribit_dvol_unavailable"
        else:
            sigma, src = iv, "deribit_dvol (FOMC in window)"
    missing = []
    if event == UNAVAILABLE:
        missing.append("fomc_calendar")
    if sigma == UNAVAILABLE:
        missing.append("sigma")
        fair = UNAVAILABLE
    elif b["kind"] == "reach":
        fair = touch_prob(inp["spot"], b["level"], sigma, T, b["direction"])
    else:
        fair = above_prob(inp["spot"], b["level"], sigma, T)
    br, n = base_rate(inp["daily"], inp["spot"], b["level"], T * 365, b["kind"], b["direction"])
    return {
        "slug": b["slug"], "kind": b["kind"], "asset": b["asset"],
        "direction": b["direction"], "level": b["level"], "end_utc": b["end_utc"],
        "fair_yes": round(fair, 6) if fair != UNAVAILABLE else UNAVAILABLE,
        "model": "touch=2N(-|ln(X/S)|/(σ√T))" if b["kind"] == "reach" else "N(d2)",
        "spot": inp["spot"], "spot_source": inp["source"], "spot_ts": inp["ts"],
        "sigma": sigma, "sigma_source": src, "T_years": round(T, 6),
        "fomc_in_window": event, "base_rate": br, "base_rate_samples": n,
        "inputs_unavailable": missing,
        "blind_file": f"blind/{b['slug']}.json",
    }


def run(markets=None, now=None):
    """對 blind/ 每個市場算 fair，寫 fair/<slug>.json。同一台北日已算過就保留（冪等）。"""
    now = now or now_utc()
    blinds = markets if markets is not None else load_blind()
    day = today_tpe(now)
    todo = []
    for b in blinds:
        p = os.path.join(DIRS["fair"], f"{b['slug']}.json")
        if os.path.exists(p) and read_json(p).get("date_taipei") == day:
            continue
        todo.append(b)
    if not todo:
        return 0
    try:
        fomc = fomc_decision_days()
    except Exception:
        fomc = None
    inputs, ivs = {}, {}
    for a in sorted({b["asset"] for b in todo}):
        inputs[a] = market_inputs(a)
        try:
            ivs[a] = deribit_iv(a)
        except Exception:
            ivs[a] = None
    for b in todo:
        f = price_one(b, inputs[b["asset"]], ivs[b["asset"]], fomc, now)
        f["date_taipei"] = day
        f["ts"] = stamp()
        write_json(os.path.join(DIRS["fair"], f"{b['slug']}.json"), f)
    return len(todo)


if __name__ == "__main__":
    print(f"fair written: {run()}")

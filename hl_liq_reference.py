"""hl_liq_reference.py — Hyperliquid 真實持倉的清算價分佈（**僅供參考的證據**）。

硬規定（DESK_RULES 規則 6 與「沒有清算熱力圖 → SKIP」不變）：
  * 這份資料**不是** `liquidation_clusters`：不寫進那個鍵、不餵給 strategies 的清算介面、不是 S1/S2 的訊號。
  * 它只是「Hyperliquid 排行榜前 N 大帳戶的 BTC/ETH 持倉清算價」的抽樣，涵蓋率遠小於全市場
    （輸出會附 sample 名目金額 ÷ 該幣 OI 的涵蓋率），且 cross margin 帳戶的清算價常為 null（已計入 no_liq_px）。
  * 只用公開、免 key 的端點：leaderboard 檔 + POST /info clearinghouseState + metaAndAssetCtxs（皆唯讀）。
  * 限流：固定最小間隔 + 429/5xx 指數退避（尊重 Retry-After）+ 連續 429 時自動放慢；絕不並行。
"""
import json
import time

import requests

from common import _S, UNAVAILABLE, stamp

LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
HL = "https://api.hyperliquid.xyz/info"
COINS = ("BTC", "ETH")
# 清算價相對現價的分段（%）：負＝低於現價（多單被清），正＝高於現價（空單被清）
BANDS = (-100, -30, -20, -10, -5, -3, 0, 3, 5, 10, 20, 30, 1000)


class Throttle:
    """最小請求間隔 + 退避。sleep 可注入以便測試。"""

    def __init__(self, min_interval=0.4, max_interval=3.0, max_retries=6, sleep=time.sleep, clock=time.monotonic):
        self.min_interval = min_interval
        self.interval = min_interval
        self.max_interval = max_interval
        self.max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self.stats = {"requests": 0, "http_429": 0, "http_5xx": 0, "retries": 0, "failed": 0}

    def _wait(self):
        if self._last is not None:
            gap = self.interval - (self._clock() - self._last)
            if gap > 0:
                self._sleep(gap)
        self._last = self._clock()

    def post(self, session, url, payload, timeout=30):
        backoff = 2.0
        for attempt in range(self.max_retries + 1):
            self._wait()
            self.stats["requests"] += 1
            try:
                r = session.post(url, json=payload, timeout=timeout)
            except requests.RequestException:
                r = None
            code = getattr(r, "status_code", None)
            if code == 200:
                # 順利就慢慢把間隔降回基準
                self.interval = max(self.min_interval, self.interval * 0.9)
                return r.json()
            if code == 429 or code is None or (code and code >= 500):
                self.stats["http_429" if code == 429 else "http_5xx"] += 1
                self.interval = min(self.max_interval, self.interval * 1.5)
                if attempt == self.max_retries:
                    break
                self.stats["retries"] += 1
                ra = None
                try:
                    ra = float(r.headers.get("Retry-After")) if r is not None and r.headers.get("Retry-After") else None
                except ValueError:
                    ra = None
                self._sleep(ra if ra is not None else backoff)
                backoff = min(backoff * 2, 60)
                continue
            self.stats["failed"] += 1
            raise RuntimeError(f"POST {url} HTTP {code}")
        self.stats["failed"] += 1
        raise RuntimeError(f"POST {url} 重試 {self.max_retries} 次後仍失敗（429/5xx/網路）")


def fetch_leaderboard(session=_S):
    r = session.get(LEADERBOARD, timeout=120)
    r.raise_for_status()
    rows = r.json()["leaderboardRows"]
    rows.sort(key=lambda x: -float(x["accountValue"]))
    return rows


def distribution(positions, marks, oi_coin):
    """positions: [{coin, szi, val, liq}]；marks: {coin: markPx}；oi_coin: {coin: OI（幣）}。純函式，方便測試。"""
    out = {}
    for c in COINS:
        mark = marks.get(c)
        ps = [p for p in positions if p["coin"] == c]
        tot = sum(p["val"] for p in ps)
        with_liq = [p for p in ps if p["liq"] is not None]
        buckets = [{"from_pct": BANDS[i], "to_pct": BANDS[i + 1], "notional_usd": 0.0, "n": 0}
                   for i in range(len(BANDS) - 1)]
        within = {3: 0.0, 5: 0.0, 10: 0.0}
        long_below = short_above = 0.0
        for p in with_liq:
            if not mark:
                break
            pct = (p["liq"] / mark - 1) * 100
            for b in buckets:
                if b["from_pct"] <= pct < b["to_pct"]:
                    b["notional_usd"] += p["val"]
                    b["n"] += 1
                    break
            for w in within:
                if abs(pct) <= w:
                    within[w] += p["val"]
            if p["szi"] > 0:
                long_below += p["val"]
            else:
                short_above += p["val"]
        oi_usd = oi_coin.get(c, 0) * mark if mark else None
        out[c] = {
            "mark_px": mark,
            "positions": len(ps), "sample_notional_usd": round(tot, 2),
            "with_liq_px": len(with_liq), "no_liq_px": len(ps) - len(with_liq),
            "no_liq_px_notional_usd": round(tot - sum(p["val"] for p in with_liq), 2),
            "long_liq_notional_usd": round(long_below, 2), "short_liq_notional_usd": round(short_above, 2),
            "liq_within_pct_notional_usd": {f"±{k}%": round(v, 2) for k, v in within.items()},
            "buckets_vs_mark": [dict(b, notional_usd=round(b["notional_usd"], 2)) for b in buckets],
            "venue_oi_usd": round(oi_usd, 2) if oi_usd else None,
            "coverage_of_oi": round(tot / oi_usd, 4) if oi_usd else None,
        }
    return out


def scan(top_n=300, throttle=None, session=_S, leaderboard=None):
    """回傳證據項（含來源、時間、reference_only）；任何整體性失敗回 unavailable。"""
    th = throttle or Throttle()
    src = f"{LEADERBOARD} + POST {HL} (clearinghouseState, metaAndAssetCtxs)"
    try:
        rows = leaderboard if leaderboard is not None else fetch_leaderboard(session)
        meta, ctxs = th.post(session, HL, {"type": "metaAndAssetCtxs"})
        marks, oi = {}, {}
        for u, c in zip(meta["universe"], ctxs):
            if u["name"] in COINS:
                marks[u["name"]] = float(c["markPx"])
                oi[u["name"]] = float(c["openInterest"])
        positions, errors, done = [], 0, 0
        t0 = time.time()
        for r in rows[:top_n]:
            try:
                s = th.post(session, HL, {"type": "clearinghouseState", "user": r["ethAddress"]})
            except Exception:
                errors += 1
                continue
            done += 1
            for ap in s.get("assetPositions", []):
                p = ap["position"]
                if p["coin"] in COINS:
                    liq = p.get("liquidationPx")
                    positions.append({"coin": p["coin"], "szi": float(p["szi"]), "val": float(p["positionValue"]),
                                      "liq": float(liq) if liq not in (None, "") else None})
        if done == 0:
            raise RuntimeError("沒有任何帳戶查詢成功")
        dist = distribution(positions, marks, oi)
        return {"value": dist, "source": src, "fetched_at": stamp(), "reference_only": True,
                "accounts_requested": min(top_n, len(rows)), "accounts_ok": done, "accounts_failed": errors,
                "throttle": dict(th.stats, min_interval_s=th.min_interval), "scan_seconds": round(time.time() - t0, 1),
                "note": "僅供參考：排行榜前 N 大帳戶抽樣，非全市場清算熱力圖；不是 liquidation_clusters，不進任何策略訊號"}
    except Exception as e:
        return {"value": UNAVAILABLE, "source": src, "reason": str(e)[:200], "fetched_at": stamp(),
                "reference_only": True}


if __name__ == "__main__":
    import argparse
    import os
    from common import DIRS, write_json
    ap = argparse.ArgumentParser(description="Hyperliquid 清算價分佈（僅參考）→ evidence/hl_liq_reference.json")
    ap.add_argument("--top", type=int, default=300)
    ap.add_argument("--interval", type=float, default=0.4)
    a = ap.parse_args()
    res = scan(a.top, Throttle(min_interval=a.interval))
    write_json(os.path.join(DIRS["evidence"], "hl_liq_reference.json"), res)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:3000])

"""evidence.py — 盤面證據（tape），只用免費公開來源。每個數字附來源 URL 與抓取時間。
抓不到就寫 unavailable 與原因（依 DESK_RULES 第 6 條，用到它的交易會 SKIP）。
evidence/ 只准經 gate.read_evidence() 讀。"""
import os

from common import (DIRS, UNAVAILABLE, _S, get_json, http_json, stamp,
                    write_json)
from quant import fomc_decision_days, FOMC_URL, DERIBIT

ASSETS = ("BTC", "ETH")
BFUT = "https://fapi.binance.com/fapi/v1"
HL = "https://api.hyperliquid.xyz/info"
FARSIDE = {"BTC": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
           "ETH": "https://farside.co.uk/ethereum-etf-flow-all-data/"}


def item(value, source, unit=None, **extra):
    d = {"value": value, "source": source, "fetched_at": stamp()}
    if unit:
        d["unit"] = unit
    d.update(extra)
    return d


def na(source, reason):
    return {"value": UNAVAILABLE, "source": source, "reason": reason,
            "fetched_at": stamp()}


def _try(fn, source):
    try:
        return fn()
    except Exception as e:  # 任何失敗都記原因，不編數字
        return na(source, str(e)[:200])


def binance_funding(asset):
    url = f"{BFUT}/premiumIndex?symbol={asset}USDT"
    d = get_json(url, retries=1)
    return item(float(d["lastFundingRate"]), url, "per 8h")


def binance_oi(asset):
    url = f"{BFUT}/openInterest?symbol={asset}USDT"
    d = get_json(url, retries=1)
    return item(float(d["openInterest"]), url, asset)


def hyperliquid(assets):
    meta, ctxs = http_json("POST", HL, json={"type": "metaAndAssetCtxs"})
    out = {}
    for u, c in zip(meta["universe"], ctxs):
        if u["name"] in assets:
            src = f"{HL} (POST type=metaAndAssetCtxs)"
            out[u["name"]] = {
                "funding": item(float(c["funding"]), src, "per 1h",
                                per_8h=float(c["funding"]) * 8),
                "oi": item(float(c["openInterest"]), src, u["name"],
                           mark_px=float(c["markPx"])),
            }
    return out


def deribit_dvol(asset):
    from quant import deribit_iv
    return item(deribit_iv(asset), f"{DERIBIT}?currency={asset}&resolution=3600",
                "annualized")


def farside(asset):
    url = FARSIDE[asset]
    r = _S.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200 or "Just a moment" in r.text[:2000]:
        raise RuntimeError(f"HTTP {r.status_code}（Cloudflare 擋自動抓取）")
    raise RuntimeError("頁面格式未解析（尚未實作表格解析）")


def collect():
    ev = {"fetched_at": stamp(), "assets": {}, "global": {}}
    try:
        hl = hyperliquid(ASSETS)
    except Exception as e:
        hl = {a: {"funding": na(HL, str(e)[:200]), "oi": na(HL, str(e)[:200])} for a in ASSETS}
    for a in ASSETS:
        ev["assets"][a] = {
            "binance_funding": _try(lambda: binance_funding(a), f"{BFUT}/premiumIndex"),
            "binance_oi": _try(lambda: binance_oi(a), f"{BFUT}/openInterest"),
            "hyperliquid_funding": hl.get(a, {}).get("funding", na(HL, "asset missing")),
            "hyperliquid_oi": hl.get(a, {}).get("oi", na(HL, "asset missing")),
            "deribit_dvol": _try(lambda: deribit_dvol(a), DERIBIT),
            "etf_flow_prev_day": _try(lambda: farside(a), FARSIDE[a]),
            "liquidation_clusters": na("none", "沒有免費的清算熱力圖來源（文章用 Minara 付費工具）"),
            "exchange_flows": na("none", "沒有免費的交易所流向來源"),
        }
    ev["global"]["fomc_decision_days"] = _try(
        lambda: item(fomc_decision_days(), FOMC_URL), FOMC_URL)
    ev["global"]["macro_releases_today"] = na(
        "https://www.bls.gov/schedule/", "BLS 發布日程頁擋自動抓取（HTTP 403），沒有其他免費 API")
    return ev


def write(ev):
    ts = ev["fetched_at"]["utc"].replace("-", "").replace(":", "")
    write_json(os.path.join(DIRS["evidence"], f"evidence_{ts}.json"), ev)
    write_json(os.path.join(DIRS["evidence"], "latest.json"), ev)


if __name__ == "__main__":
    e = collect()
    write(e)
    for a, items in e["assets"].items():
        for k, v in items.items():
            print(a, k, v["value"] if v["value"] == UNAVAILABLE else v["value"], v.get("reason", ""))
    print("fomc", str(e["global"]["fomc_decision_days"]["value"])[:60])

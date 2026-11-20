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


OKX = "https://www.okx.com/api/v5/public"
DERIBIT_API = "https://www.deribit.com/api/v2/public"
BTCETF = "https://btcetfdata.com/api/v1/current"
NASDAQ_CAL = "https://api.nasdaq.com/api/calendar/economicevents"
MACRO_KEYWORDS = ("consumer price", "cpi", "producer price", "ppi", "nonfarm", "unemployment rate",
                  "pce", "gdp", "fomc", "retail sales", "ism ", "jobless claims", "payroll")


def okx(asset):
    """OKX 永續（公開 API，無需 key）：資金費率（換算成每 8h）與 OI。"""
    inst = f"{asset}-USDT-SWAP"
    fu = f"{OKX}/funding-rate?instId={inst}"
    f = get_json(fu, retries=1)["data"][0]
    hours = (int(f["nextFundingTime"]) - int(f["fundingTime"])) / 3.6e6
    rate = float(f["fundingRate"])
    oi_url = f"{OKX}/open-interest?instType=SWAP&instId={inst}"
    o = get_json(oi_url, retries=1)["data"][0]
    return (item(rate * 8 / hours, fu, "per 8h", raw_rate=rate, interval_hours=hours),
            item(float(o["oiCcy"]), oi_url, asset, oi_usd=float(o["oiUsd"])))

BITGET = "https://api.bitget.com/api/v2/mix/market"
GATE = "https://api.gateio.ws/api/v4/futures/usdt/contracts"
DYDX = "https://indexer.dydx.trade/v4/perpetualMarkets"


def bitget(asset):
    """Bitget USDT 永續（公開 API，無需 key）：資金費率（換算成每 8h）與 OI（單位＝幣）。"""
    sym = f"{asset}USDT"
    fu = f"{BITGET}/current-fund-rate?symbol={sym}&productType=USDT-FUTURES"
    f = get_json(fu, retries=1)
    if f.get("code") != "00000" or not f.get("data"):
        raise RuntimeError(f"Bitget funding code={f.get('code')} msg={f.get('msg')}")
    f = f["data"][0]
    hours = float(f.get("fundingRateInterval") or 8)
    rate = float(f["fundingRate"])
    oi_url = f"{BITGET}/open-interest?symbol={sym}&productType=USDT-FUTURES"
    o = get_json(oi_url, retries=1)
    if o.get("code") != "00000" or not o.get("data", {}).get("openInterestList"):
        raise RuntimeError(f"Bitget OI code={o.get('code')} msg={o.get('msg')}")
    size = float(o["data"]["openInterestList"][0]["size"])
    return (item(rate * 8 / hours, fu, "per 8h", raw_rate=rate, interval_hours=hours),
            item(size, oi_url, asset))


def gate(asset):
    """Gate USDT 永續合約（公開 API，無需 key）：資金費率（funding_interval 秒 → 每 8h）；
    OI＝position_size（張）× quanto_multiplier（幣/張）。"""
    url = f"{GATE}/{asset}_USDT"
    c = get_json(url, retries=1)
    hours = float(c.get("funding_interval") or 28800) / 3600
    rate = float(c["funding_rate"])
    oi_coin = float(c["position_size"]) * float(c["quanto_multiplier"])
    return (item(rate * 8 / hours, url, "per 8h", raw_rate=rate, interval_hours=hours),
            item(oi_coin, url, asset, position_size_contracts=float(c["position_size"]),
                 quanto_multiplier=float(c["quanto_multiplier"])))


def dydx(asset):
    """dYdX v4 indexer（公開 API，無需 key）：nextFundingRate 是每 1h → ×8；OI 單位＝幣。規模小，排最後。"""
    url = f"{DYDX}?ticker={asset}-USD"
    m = get_json(url, retries=1)["markets"][f"{asset}-USD"]
    if m.get("status") != "ACTIVE":
        raise RuntimeError(f"dYdX {asset}-USD status={m.get('status')}")
    rate = float(m["nextFundingRate"])
    return (item(rate * 8, url, "per 8h", raw_rate_1h=rate, interval_hours=1),
            item(float(m["openInterest"]), url, asset))

def okx_premarket():
    """OKX pre_market 永續（S4 盤前價的 v2 來源；v1 只留證據，不接任何策略）。
    列出 ruleType=pre_market 的合約，再逐一抓 ticker。價格單位＝USDT／單位標的（不是 FDV，換算需要供給量，v2 再說）。
    抓不到就 unavailable；單一合約 ticker 失敗只標那一檔。"""
    iurl = f"{OKX}/instruments?instType=SWAP"
    ins = get_json(iurl, retries=1)
    if ins.get("code") != "0":
        raise RuntimeError(f"OKX instruments code={ins.get('code')} msg={ins.get('msg')}")
    pm = [x for x in ins["data"] if x.get("ruleType") == "pre_market"]
    out = []
    for x in pm:
        turl = f"https://www.okx.com/api/v5/market/ticker?instId={x['instId']}"
        rec = {"instId": x["instId"], "state": x.get("state"), "listTime_ms": x.get("listTime"),
               "ctVal": x.get("ctVal"), "ctValCcy": x.get("ctValCcy"), "settleCcy": x.get("settleCcy"),
               "source": turl}
        try:
            t = get_json(turl, retries=1)
            if t.get("code") != "0" or not t.get("data"):
                raise RuntimeError(f"code={t.get('code')} msg={t.get('msg')}")
            t = t["data"][0]
            rec.update(last=float(t["last"]), bid=float(t["bidPx"]) if t.get("bidPx") else None,
                       ask=float(t["askPx"]) if t.get("askPx") else None,
                       vol24h=t.get("vol24h"), ticker_ts_ms=t["ts"], fetched_at=stamp())
        except Exception as e:
            rec.update(last=UNAVAILABLE, reason=str(e)[:200], fetched_at=stamp())
        out.append(rec)
    return item(out, iurl, "USDT per underlying unit (not FDV)", reference_only=True,
                note="S4（v2）盤前價來源的證據；v1 無任何策略讀取", n_instruments=len(out))


def deribit_perp(asset):
    """Deribit 永續 ticker（公開 API）：funding_8h 與 open_interest。"""
    url = f"{DERIBIT_API}/ticker?instrument_name={asset}-PERPETUAL"
    r = get_json(url, retries=1)["result"]
    return (item(float(r["funding_8h"]), url, "per 8h"),
            item(float(r["open_interest"]), url, "USD notional (Deribit perp contracts)"))


def btc_etf_prev_day():
    """前一美東交易日美國現貨 BTC ETF 淨流量（BTC 數量，加總各檔 issuer 公布的持倉變化）。
    來源 btcetfdata.com（第三方彙整 issuer 網站，免 key）。要求 9 檔全部 dt == 前一交易日
    且無 error，否則 unavailable（不拿不完整的總和充數）。"""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from common import now_utc
    d = get_json(BTCETF, retries=2)
    et_today = now_utc().astimezone(ZoneInfo("America/New_York")).date()
    prev = et_today - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    funds = d["data"]
    late = {k: v["dt"] for k, v in funds.items() if v["dt"] != prev.isoformat() or v["error"]}
    if late:
        raise RuntimeError(f"incomplete: 前一交易日 {prev} 尚未全數公布，落後/錯誤的基金 {late}")
    total = sum(v["change"] for v in funds.values())
    return item(total, BTCETF, "BTC (sum of issuer holdings change)", trading_day=prev.isoformat(),
                funds={k: v["change"] for k, v in funds.items()}, batch_ts=d.get("batch_ts"),
                note="第三方彙整 issuer 網站；非 Farside 數字，單位為 BTC")


def macro_events(days=8):
    """Nasdaq 公開經濟日曆（api.nasdaq.com，非正式文件的公開端點）：未來 days 天美國高影響事件。
    欄位標 gmt，但時間與實際發布時刻（美東）吻合，原樣記錄 raw_time。"""
    from datetime import timedelta
    from common import now_utc
    out, base = [], now_utc().date()
    for i in range(days):
        day = base + timedelta(days=i)
        url = f"{NASDAQ_CAL}?date={day.isoformat()}"
        resp = get_json(url, retries=1, headers={"User-Agent": "Mozilla/5.0"})
        if resp.get("data") is None:
            codes = [c.get("code") for c in (resp.get("status") or {}).get("bCodeMessage") or []]
            if 1002 in codes:  # "No record found" = 當天沒有事件（例如週日）
                continue
            raise RuntimeError(f"nasdaq calendar {day}: unexpected response {str(resp)[:150]}")
        rows = resp["data"]["rows"] or []
        for r in rows:
            n = r["eventName"].lower()
            if r["country"] == "United States" and any(k in n for k in MACRO_KEYWORDS) \
                    and not any(x in n for x in ("speaks", "gdpnow", "dallas fed")):
                out.append({"date": day.isoformat(), "raw_time": r["gmt"], "event": r["eventName"]})
    return item(out, f"{NASDAQ_CAL}?date=<YYYY-MM-DD>", "US high-impact events",
                note="raw_time 欄位標 gmt，實際對應美東發布時刻")


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


def etf_flow(asset):
    if asset == "BTC":
        return btc_etf_prev_day()
    raise RuntimeError("ETH 現貨 ETF 流量：Farside 403（Cloudflare）、SoSoValue 403，找不到免 key 且不被擋的公開來源")


def farside(asset):  # 保留作為紀錄：Farside 目前被 Cloudflare 擋（403），不嘗試繞過
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
        okx_f, okx_o = (None, None)
        try:
            okx_f, okx_o = okx(a)
        except Exception as e:
            okx_f = okx_o = na(OKX, str(e)[:200])
        der_f = der_o = None
        try:
            der_f, der_o = deribit_perp(a)
        except Exception as e:
            der_f = der_o = na(DERIBIT_API, str(e)[:200])
        extra = {}
        for name, fn, src in (("bitget", bitget, BITGET), ("gate", gate, GATE), ("dydx", dydx, DYDX)):
            try:
                extra[f"{name}_funding"], extra[f"{name}_oi"] = fn(a)
            except Exception as e:
                extra[f"{name}_funding"] = extra[f"{name}_oi"] = na(src, str(e)[:200])
        ev["assets"][a] = {
            "binance_funding": _try(lambda: binance_funding(a), f"{BFUT}/premiumIndex"),
            "binance_oi": _try(lambda: binance_oi(a), f"{BFUT}/openInterest"),
            "hyperliquid_funding": hl.get(a, {}).get("funding", na(HL, "asset missing")),
            "hyperliquid_oi": hl.get(a, {}).get("oi", na(HL, "asset missing")),
            "okx_funding": okx_f, "okx_oi": okx_o,
            "deribit_funding": der_f, "deribit_oi": der_o,
            **extra,
            "deribit_dvol": _try(lambda: deribit_dvol(a), DERIBIT),
            "etf_flow_prev_day": _try(lambda: etf_flow(a), BTCETF),
            "liquidation_clusters": na("none", "沒有免費的清算熱力圖來源（文章用 Minara 付費工具）"),
            "exchange_flows": na("none", "沒有免費的交易所流向來源"),
        }
    ev["global"]["fomc_decision_days"] = _try(
        lambda: item(fomc_decision_days(), FOMC_URL), FOMC_URL)
    ev["global"]["macro_events_next8d"] = _try(macro_events, NASDAQ_CAL)
    ev["global"]["okx_premarket"] = _try(okx_premarket, f"{OKX}/instruments?instType=SWAP")
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

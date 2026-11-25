"""strategies.py — 第一版：S1 觸價、S2 賣樂透、S3 同日梯子與鏡像（規則見 DESK_RULES.md）。
S4 盤前 FDV、S5 已公布事實排在第二版。

每個 decide_* 回傳 dict：decision（TRADE / NO_EDGE / SKIP）、reason、side、edge、threshold。
任何需要的輸入為 unavailable → SKIP（DESK_RULES 第 6 條）。"""
from common import UNAVAILABLE, parse_iso, now_utc
import fees
import risk_gate

FAR_STRIKE_MAX_FAIR = 0.10   # S2「遠檔位」：fair_touch ≤ 10%（程式員的操作定義，負責人可改）
FUNDING_EXTREME_8H = 5 * 0.0001  # S2 否決：|資金費率| ≥ 5 × 0.01%/8h
MIRROR_LO, MIRROR_HI = 1.6, 2.4
LIQ_CLUSTER_MIN_USD = 10e9   # S1「≥ $10B 清算叢集」（DESK_RULES S1）
LIQ_NEAR_PCT = 0.03          # S2 否決「關卡附近」的操作定義：關卡 ±3% 內（負責人可改）


def liq_clusters_value(ea):
    """清算叢集介面。evidence 的 liquidation_clusters.value 若有值，格式為
    [{"price": float, "usd": float}, ...]（價格水平與該水平上的預估清算金額）；
    資料源缺 → unavailable（呼叫端必須 SKIP，不用任何代理指標頂替）。"""
    liq = ea["liquidation_clusters"]
    if _na(liq["value"]):
        return UNAVAILABLE, liq.get("reason")
    return liq["value"], None


def liq_between(clusters, spot, level):
    """價格 spot 與關卡 level 之間（含關卡）的清算總額。"""
    lo, hi = sorted((spot, level))
    return sum(c["usd"] for c in clusters if lo <= c["price"] <= hi)


def liq_near(clusters, level, pct=LIQ_NEAR_PCT):
    return sum(c["usd"] for c in clusters if abs(c["price"] / level - 1) <= pct)


def _na(x):
    return x is None or x == UNAVAILABLE


def _base(fair, row, now=None):
    q, mid = fair.get("fair_yes"), row["yes_book"].get("mid")
    if _na(q):
        return None, {"decision": "SKIP", "reason": f"fair unavailable: {fair.get('inputs_unavailable')}"}
    if fair.get("inputs_unavailable"):
        return None, {"decision": "SKIP", "reason": f"input unavailable: {fair['inputs_unavailable']}"}
    if _na(mid):
        return None, {"decision": "SKIP", "reason": "mid unavailable (one-sided book)"}
    fee = fees.taker_fee_per_share(mid, when=now or now_utc())
    return (q, mid, fee, fee + risk_gate.EDGE_BUFFER), None


def _hours_left(row, now):
    return (parse_iso(row["end_utc"]) - now).total_seconds() / 3600


# 「取第一個可用」。資金費率一律換成每 8h；dYdX 規模小，排最後。
FUNDING_ORDER = ("binance_funding", "okx_funding", "bitget_funding", "gate_funding",
                 "deribit_funding", "hyperliquid_funding", "dydx_funding")
OI_ORDER = ("binance_oi", "okx_oi", "bitget_oi", "gate_oi", "hyperliquid_oi", "deribit_oi", "dydx_oi")


def _funding_8h(ev_a):
    """資金費率（每 8h）：依序取第一個可用的免費來源（見 FUNDING_ORDER）。"""
    for k in FUNDING_ORDER:
        v = ev_a.get(k)
        if v and not _na(v["value"]):
            return (v["per_8h"] if k == "hyperliquid_funding" else v["value"]), k.split("_")[0]
    return UNAVAILABLE, None


def _oi(ev_a):
    for k in OI_ORDER:
        v = ev_a.get(k)
        if v and not _na(v["value"]):
            return v["value"], k.split("_")[0]
    return UNAVAILABLE, None


def decide_s1(fair, row, ev, now=None):
    """S1 只買 YES：訊號是「價格與關卡之間 ≥ $10B 清算叢集」（DESK_RULES S1 訊號），
    叢集把價格吸向關卡 = 會觸價 = YES 方向。沒有叢集就沒有 S1 訊號，所以 S1 不出 NO 單；
    遠檔位買 NO 屬於 S2（賣樂透），由 decide_s2 判斷並套用它自己的否決條件。
    edge 一律記買進那一側的邊際（YES：fair − mid）。"""
    now = now or now_utc()
    base, out = _base(fair, row, now)
    if out:
        return out
    q, mid, fee, thr = base
    edge = q - mid
    d = {"side": "YES", "edge": round(edge, 4), "threshold": round(thr, 4)}
    if edge <= thr:
        why = f"YES edge {edge:.4f} <= fee+2pp {thr:.4f}"
        if -edge > thr:
            why += " (S1 buys YES only; NO side belongs to S2)"
        return dict(d, decision="NO_EDGE", reason=why)
    if _hours_left(row, now) <= 24:
        return dict(d, decision="NO_EDGE", reason="within 24h of expiry (exit window)")
    clusters, why = liq_clusters_value(ev["assets"][row["asset"]])
    if clusters == UNAVAILABLE:
        return dict(d, decision="SKIP", reason=f"tape unavailable: liquidation_clusters ({why})")
    usd = liq_between(clusters, fair["spot"], row["level"])
    d["liq_between_usd"] = usd
    if usd < LIQ_CLUSTER_MIN_USD:
        return dict(d, decision="NO_EDGE", reason=f"tape not confirming: cluster between spot and level ${usd:,.0f} < ${LIQ_CLUSTER_MIN_USD:,.0f}")
    return dict(d, decision="TRADE", reason=f"edge > fee+2pp, tape confirms (cluster ${usd:,.0f})")


def decide_s2(fair, row, ev, now=None):
    now = now or now_utc()
    base, out = _base(fair, row, now)
    if out:
        return out
    q, mid, fee, thr = base
    edge = mid - q  # 買 NO 的邊際
    d = {"side": "NO", "edge": round(edge, 4), "threshold": round(thr, 4)}
    if q > 0 and mid < 2 * q or q == 0 and mid <= 0:
        return dict(d, decision="NO_EDGE", reason=f"no longshot signal: mid {mid} < 2×fair {q:.4f}")
    if edge <= thr:
        return dict(d, decision="NO_EDGE", reason=f"mid-fair {edge:.4f} <= fee+2pp {thr:.4f}")
    if _hours_left(row, now) <= 24:
        return dict(d, decision="NO_EDGE", reason="within 24h of expiry (exit window)")
    if fair.get("fomc_in_window") is True:
        return dict(d, decision="SKIP", reason="veto: FOMC meeting inside window")
    ea = ev["assets"][row["asset"]]
    clusters, why = liq_clusters_value(ea)
    if clusters == UNAVAILABLE:
        return dict(d, decision="SKIP", reason=f"tape unavailable: liquidation_clusters ({why})")
    near = liq_near(clusters, row["level"])
    if near >= LIQ_CLUSTER_MIN_USD:
        return dict(d, decision="SKIP", reason=f"veto: liquidation cluster ${near:,.0f} within {LIQ_NEAR_PCT:.0%} of strike")
    f8, src = _funding_8h(ea)
    if _na(f8):
        return dict(d, decision="SKIP", reason="tape unavailable: funding")
    if abs(f8) >= FUNDING_EXTREME_8H:
        return dict(d, decision="SKIP", reason=f"veto: extreme funding {f8:.6f}/8h ({src})")
    return dict(d, decision="TRADE", reason="longshot, edge > fee+2pp, no veto")


def decide_s3(fair, row, ev, now=None):
    base, out = _base(fair, row, now)
    if out:
        return out
    q, mid, fee, thr = base
    side = "YES" if q > mid else "NO"
    edge = (q - mid) if side == "YES" else (mid - q)   # 買進那一側的邊際，TRADE 時一定 > 0
    d = {"side": side, "edge": round(edge, 4), "threshold": round(thr, 4)}
    if edge <= thr:
        return dict(d, decision="NO_EDGE", reason=f"|fair-mid| {edge:.4f} <= fee+2pp {thr:.4f}")
    ea = ev["assets"][row["asset"]]
    f8, _ = _funding_8h(ea)
    oi, _ = _oi(ea)
    missing = [n for n, v in (("funding", f8), ("open_interest", oi),
                              ("etf_flow_prev_day", ea["etf_flow_prev_day"]["value"]),
                              ("macro_calendar", ev["global"]["macro_events_next8d"]["value"]))
               if _na(v)]
    if missing:
        return dict(d, decision="SKIP", reason=f"tape unavailable: {', '.join(missing)}")
    # tape 選邊（程式員的操作定義）：資金費率與 ETF 流量都和方向相反 → 否決
    etf = ea["etf_flow_prev_day"]["value"]
    against = (side == "YES" and f8 < 0 and etf < 0) or (side == "NO" and f8 > 0 and etf > 0)
    if against:
        return dict(d, decision="SKIP", reason="veto: tape (funding & ETF flow) against side")
    return dict(d, decision="TRADE", reason="edge > fee+2pp, tape ok")


def mirror_pairs(rows):
    """同資產、同關卡、同一天的 hit（reach）與 above 市場配對，回傳 {above_slug: info}。
    市價比 hit_mid / above_mid（關卡低於現價時用 dip 與 1−above）。"""
    import re
    def day(r):
        m = re.search(r"on (\w+ \d+)", r["question"])
        return m.group(1) if m else None
    hits = {}
    for r in rows:
        if r["kind"] == "reach" and day(r):
            hits[(r["asset"], r["level"], day(r), r["direction"])] = r
    out = {}
    for r in rows:
        if r["kind"] != "above" or not day(r):
            continue
        a_mid = r["yes_book"].get("mid")
        for direction in ("up", "down"):
            h = hits.get((r["asset"], r["level"], day(r), direction))
            if not h:
                continue
            h_mid = h["yes_book"].get("mid")
            base = a_mid if direction == "up" else (1 - a_mid if not _na(a_mid) else a_mid)
            if _na(h_mid) or _na(base) or base <= 0:
                out[r["slug"]] = {"hit_slug": h["slug"], "ratio": UNAVAILABLE, "flag": False}
                continue
            ratio = h_mid / base
            out[r["slug"]] = {"hit_slug": h["slug"], "ratio": round(ratio, 3),
                              "flag": ratio < MIRROR_LO or ratio > MIRROR_HI}
    return out


def limit_for(side, row, q_side, thr):
    """maker 買單價：比同側最佳買價高一 tick，但不碰到對手最佳賣價；不超過 0.97。"""
    tick = float(row.get("tick_size") or 0.01) if row.get("tick_size") != UNAVAILABLE else 0.01
    yb = row["yes_book"]
    if side == "YES":
        bid, ask = yb["best_bid"], yb["best_ask"]
    else:
        bid = UNAVAILABLE if _na(yb["best_ask"]) else round(1 - yb["best_ask"], 6)
        ask = UNAVAILABLE if _na(yb["best_bid"]) else round(1 - yb["best_bid"], 6)
    px = (bid + tick) if not _na(bid) else (ask - tick)
    if not _na(ask):
        px = min(px, ask - tick)
    px = min(px, q_side - thr, risk_gate.MAX_BUY_PRICE - tick)
    px = round(int(px / tick + 1e-9) * tick, 6)
    return px if px >= tick else None

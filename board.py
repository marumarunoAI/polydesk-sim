"""board.py — 掃 Polymarket 公開 Gamma API 找 BTC/ETH 觸價與同日 above 市場，
再用 CLOB 公開 API 抓 YES token 訂單簿，寫進 board/。

只讀公開資料，不簽名、不下單。
注意：board/ 的內容只能經 gate.read_board() 讀（先有 fair 才准看價）。
"""
import json
import os
import re
import sys

import risk_gate

from common import (DIRS, UNAVAILABLE, get_json, http_json, iso_tpe, iso_utc,
                    now_utc, parse_iso, stamp, write_json)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
TAGS = {"BTC": 235, "ETH": 39}  # Gamma tag id: bitcoin / ethereum
DEPTH_LEVELS = 5

RE_REACH = re.compile(
    r"^Will (Bitcoin|Ethereum) (reach|hit|dip to) \$([\d,\.]+)(k?)\b", re.I)
RE_ABOVE = re.compile(
    r"^(?:Will the price of )?(Bitcoin|Ethereum) (?:be )?above \$?([\d,\.]+)(k?) on ",
    re.I)
ASSET = {"bitcoin": "BTC", "ethereum": "ETH"}


def _num(s, k):
    v = float(s.replace(",", ""))
    return v * 1000 if k.lower() == "k" else v


def classify(question):
    """回傳 (kind, asset, direction, level) 或 None。
    kind: reach（觸價，任一 1 分 K 碰到）/ above（某時刻收盤高於）。"""
    m = RE_REACH.match(question or "")
    if m:
        d = "down" if m.group(2).lower() == "dip to" else "up"
        return "reach", ASSET[m.group(1).lower()], d, _num(m.group(3), m.group(4))
    m = RE_ABOVE.match(question or "")
    if m:
        return "above", ASSET[m.group(1).lower()], "up", _num(m.group(2), m.group(3))
    return None


def excluded(event):
    """短於日線、體育、選舉、政治 → True。"""
    return risk_gate.excluded([t.get("slug") for t in event.get("tags") or []],
                              [s.get("recurrence") for s in event.get("series") or []])


def resolution_source(m, e):
    rs = (m.get("resolutionSource") or e.get("resolutionSource") or "").strip()
    if rs:
        return rs
    hit = re.search(r"resolution source for this market is ([^\n]+)",
                    m.get("description") or "", re.I)
    return hit.group(1).strip() if hit else UNAVAILABLE


def fetch_events(tag_id):
    out, cur = [], None
    for _ in range(50):
        p = {"tag_id": tag_id, "closed": "false", "limit": 100,
             "end_date_min": iso_utc(now_utc())}
        if cur:
            p["after_cursor"] = cur
        d = get_json(f"{GAMMA}/events/keyset", params=p)
        out += d.get("events") or []
        cur = d.get("next_cursor")
        if not cur or not d.get("events"):
            break
    return out


def scan_markets():
    """回傳市場清單（只有規則與中繼資料，不含任何價格）與統計。"""
    now = now_utc()
    seen, markets = set(), []
    stats = {"events": 0, "excluded_short": 0, "excluded_banned": 0,
             "unclassified_markets": 0}
    events = {}
    for tag in TAGS.values():
        for e in fetch_events(tag):
            events[e["id"]] = e
    for e in events.values():
        stats["events"] += 1
        why = excluded(e)
        if why:
            stats["excluded_short" if "daily" in why else "excluded_banned"] += 1
            continue
        for m in e.get("markets") or []:
            if m.get("closed") or not m.get("active") or m["id"] in seen:
                continue
            if not m.get("enableOrderBook") or not m.get("acceptingOrders"):
                continue
            end = parse_iso(m.get("endDate"))
            if not end or end <= now:
                continue
            q = m.get("question") or ""
            c = None if re.search(r"\bfirst\b| or \$", q, re.I) else classify(q)
            if not c:
                stats["unclassified_markets"] += 1
                continue
            seen.add(m["id"])
            kind, asset, direction, level = c
            try:
                tokens = json.loads(m.get("clobTokenIds") or "[]")
                outcomes = json.loads(m.get("outcomes") or "[]")
            except ValueError:
                tokens, outcomes = [], []
            tok = dict(zip([o.lower() for o in outcomes], tokens))
            markets.append({
                "market_id": m["id"],
                "slug": m["slug"],
                "condition_id": m.get("conditionId") or UNAVAILABLE,
                "event_slug": e.get("slug"),
                "event_title": e.get("title"),
                "question": m["question"],
                "kind": kind,
                "asset": asset,
                "direction": direction,
                "level": level,
                "rules": m.get("description") or UNAVAILABLE,
                "resolution_source": resolution_source(m, e),
                "end_utc": iso_utc(end),
                "end_taipei": iso_tpe(end),
                "yes_token": tok.get("yes", UNAVAILABLE),
                "no_token": tok.get("no", UNAVAILABLE),
                "tick_size": m.get("orderPriceMinTickSize") or UNAVAILABLE,
                "min_order_size": m.get("orderMinSize") or UNAVAILABLE,
                "tags": [t.get("slug") for t in e.get("tags") or []],
            })
    markets.sort(key=lambda x: (x["kind"], x["asset"], x["end_utc"], x["level"]))
    return markets, stats


def _levels(side, best_first_desc):
    lv = [(float(x["price"]), float(x["size"])) for x in side or []]
    lv.sort(key=lambda t: t[0], reverse=best_first_desc)
    return lv


def summarize_book(book):
    """CLOB /book 回應 → 最佳買賣、mid、前 5 檔與加總。"""
    if not book or "bids" not in book:
        return {k: UNAVAILABLE for k in
                ("best_bid", "best_ask", "mid", "bids_top5", "asks_top5",
                 "bid_depth_top5", "ask_depth_top5", "last_trade_price")}
    bids = _levels(book.get("bids"), True)
    asks = _levels(book.get("asks"), False)
    bb = bids[0][0] if bids else UNAVAILABLE
    ba = asks[0][0] if asks else UNAVAILABLE
    mid = round((bb + ba) / 2, 6) if bids and asks else UNAVAILABLE
    top = lambda lv: [{"price": p, "size": s} for p, s in lv[:DEPTH_LEVELS]]
    return {
        "best_bid": bb, "best_ask": ba, "mid": mid,
        "bids_top5": top(bids), "asks_top5": top(asks),
        "bid_depth_top5": round(sum(s for _, s in bids[:DEPTH_LEVELS]), 4),
        "ask_depth_top5": round(sum(s for _, s in asks[:DEPTH_LEVELS]), 4),
        "last_trade_price": float(book["last_trade_price"])
        if book.get("last_trade_price") not in (None, "") else UNAVAILABLE,
        "book_timestamp_ms": book.get("timestamp", UNAVAILABLE),
    }


def fetch_books(token_ids):
    """POST /books 批次抓訂單簿，回傳 {token_id: book}。"""
    out = {}
    ids = [t for t in token_ids if t and t != UNAVAILABLE]
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            res = http_json("POST", f"{CLOB}/books",
                            json=[{"token_id": t} for t in chunk])
        except RuntimeError:
            res = []
            for t in chunk:  # 退回逐筆
                try:
                    res.append(get_json(f"{CLOB}/book", params={"token_id": t}))
                except RuntimeError:
                    pass
        for b in res or []:
            out[b.get("asset_id")] = b
    return out


def snapshot(markets):
    """對每個市場抓 YES 訂單簿，回傳 board dict。"""
    fetched = stamp()
    books = fetch_books([m["yes_token"] for m in markets])
    rows = []
    for m in markets:
        row = dict(m)
        row["yes_book"] = summarize_book(books.get(m["yes_token"]))
        row["fetched_at_utc"] = fetched["utc"]
        rows.append(row)
    counts = {}
    for r in rows:
        k = f'{r["kind"]}_{r["asset"]}'
        counts[k] = counts.get(k, 0) + 1
    return {"fetched_at": fetched, "source": [GAMMA, CLOB],
            "counts": counts, "markets": rows}


def write_board(board):
    ts = board["fetched_at"]["utc"].replace("-", "").replace(":", "")
    path = os.path.join(DIRS["board"], f"board_{ts}.json")
    write_json(path, board)
    write_json(os.path.join(DIRS["board"], "latest.json"), board)
    return path


def main():
    markets, stats = scan_markets()
    board = snapshot(markets)
    path = write_board(board)
    no_book = sum(1 for r in board["markets"] if r["yes_book"]["mid"] == UNAVAILABLE)
    print(f"scan: {stats}")
    print(f"markets: {len(markets)}  counts: {board['counts']}  mid unavailable: {no_book}")
    print(f"wrote {os.path.relpath(path)} and board/latest.json")


if __name__ == "__main__":
    sys.exit(main())

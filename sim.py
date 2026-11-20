"""sim.py — 模擬 maker 限價單（tickets/）與成交判定。不簽名、不送單。

成交規則（不假設以 mid 成交）：
  我們掛「買 outcome O、限價 L」的 maker 單，只有真實市場有人賣給這個價位才算成交：
  1) 掛單後的真實成交（Polymarket Data API /v2/trades，taker 側）：
     taker 賣 O、或 taker 買另一邊（價格換算 1−p），換算價 px：
       px < L  → 整筆量可成交給我們；
       px == L → 先扣掉掛單時同價位排在我們前面的量（queue_ahead），剩下的才給我們。
  2) 目前訂單簿已經有人掛賣 ≤ L（簿子穿過我們的價）→ 依那些檔位的深度成交。
  成交量上限為剩餘股數，所以可能部分成交。maker 手續費依官方文件 = 0。"""
import glob
import os

from common import DIRS, get_json, now_utc, parse_iso, read_json, stamp, write_json
import fees

DATA_API = "https://data-api.polymarket.com/v2/trades"
CANCEL_BEFORE_H = {"S1": 24, "S2": 24, "S3": 0}  # S1/S2 到期前 24h 撤單；S3 持有到中午


def ticket_path(tid):
    return os.path.join(DIRS["tickets"], f"{tid}.json")


def book_side_for(outcome, yes_book):
    """回傳買 outcome 時「賣方」檔位 [(price, size)]（由便宜到貴）與「同側買方」檔位。"""
    bids = [(l["price"], l["size"]) for l in yes_book.get("bids_top5") or []]
    asks = [(l["price"], l["size"]) for l in yes_book.get("asks_top5") or []]
    if outcome == "YES":
        return sorted(asks), bids
    no_asks = sorted((round(1 - p, 6), s) for p, s in bids)
    no_bids = [(round(1 - p, 6), s) for p, s in asks]
    return no_asks, no_bids


def place(tid, strategy, market, outcome, limit, shares, usd, yes_book):
    """建立 ticket（冪等：同 id 已存在就不重建）。"""
    p = ticket_path(tid)
    if os.path.exists(p):
        return read_json(p), False
    sellers, same = book_side_for(outcome, yes_book)
    if sellers and sellers[0][0] <= limit:
        raise ValueError("limit would cross the book (taker) — maker only")
    queue = sum(s for px, s in same if abs(px - limit) < 1e-9)
    end = parse_iso(market["end_utc"])
    t = {
        "id": tid, "strategy": strategy, "slug": market["slug"], "asset": market["asset"],
        "kind": market["kind"], "condition_id": market["condition_id"],
        "outcome": outcome,
        "token_id": market["yes_token"] if outcome == "YES" else market["no_token"],
        "limit_price": limit, "shares": round(shares, 4), "usd": usd,
        "order_type": "maker_limit_buy (simulated)",
        "placed_at": stamp(), "end_utc": market["end_utc"],
        "cancel_at_epoch": end.timestamp() - CANCEL_BEFORE_H.get(strategy, 0) * 3600,
        "queue_ahead": queue, "status": "open", "filled_shares": 0.0,
        "fill_cost": 0.0, "fee_paid": 0.0, "fee_rate_maker": fees.MAKER_FEE_RATE,
        "last_checked_epoch": None, "fills": [],
    }
    write_json(p, t)
    return t, True


def fetch_trades(condition_id, since_epoch, max_pages=10):
    out, cur = [], None
    for _ in range(max_pages):
        params = {"condition": condition_id, "limit": 500, "taker_only": "true"}
        if cur:
            params = {"cursor": cur}
        d = get_json(DATA_API, params=params)
        rows = d.get("data") or []
        out += [r for r in rows if r["timestamp"] > since_epoch]
        cur = (d.get("pagination") or {}).get("next_cursor")
        if not rows or rows[-1]["timestamp"] <= since_epoch or not cur:
            break
    return out


def trade_px_for(outcome, trade):
    """把一筆 taker 成交換算成「對我們買單」的價格；不相關回傳 None。"""
    mine = trade["outcome"].upper() == outcome
    if mine and trade["side"] == "SELL":
        return float(trade["price"])
    if not mine and trade["side"] == "BUY":
        return round(1 - float(trade["price"]), 6)
    return None


def apply_fills(t, trades, yes_book, now=None):
    """純函式：依成交紀錄與目前訂單簿更新 ticket（可單元測試）。"""
    now = now or now_utc()
    if t["status"] in ("filled", "cancelled"):
        return t
    since = t["last_checked_epoch"] or t["placed_at"]["epoch"]
    L = t["limit_price"]
    remaining = t["shares"] - t["filled_shares"]
    through = at = 0.0
    for tr in trades:
        if tr["timestamp"] <= since:
            continue
        px = trade_px_for(t["outcome"], tr)
        if px is None:
            continue
        if px < L - 1e-9:
            through += float(tr["size"])
        elif abs(px - L) < 1e-9:
            at += float(tr["size"])
    at_ours = max(0.0, at - t["queue_ahead"])
    t["queue_ahead"] = max(0.0, t["queue_ahead"] - at)
    sellers, _ = book_side_for(t["outcome"], yes_book or {})
    crossed = sum(s for px, s in sellers if px <= L + 1e-9)
    got = min(remaining, through + at_ours + crossed)
    if got > 0:
        t["fills"].append({"at": stamp(now), "shares": round(got, 4), "price": L,
                           "basis": {"trades_through": through, "trades_at_limit_after_queue": at_ours,
                                     "book_crossed_depth": crossed}})
        t["filled_shares"] = round(t["filled_shares"] + got, 4)
        t["fill_cost"] = round(t["fill_cost"] + got * L, 6)
        t["fee_paid"] += fees.maker_fee(got, L)
    if t["filled_shares"] >= t["shares"] - 1e-9:
        t["status"] = "filled"
    elif now.timestamp() >= t["cancel_at_epoch"]:
        t["status"] = "cancelled" if t["filled_shares"] == 0 else "partial_cancelled"
    elif t["filled_shares"] > 0:
        t["status"] = "partial"
    t["last_checked_epoch"] = now.timestamp()
    return t


def open_tickets():
    out = []
    for p in sorted(glob.glob(os.path.join(DIRS["tickets"], "*.json"))):
        t = read_json(p)
        if t["status"] in ("open", "partial"):
            out.append(t)
    return out


def check_all(board_rows):
    """對每張未完成 ticket 用真實成交 + 目前訂單簿判定成交。board_rows: {slug: row}。"""
    done = []
    for t in open_tickets():
        try:
            trades = fetch_trades(t["condition_id"], t["last_checked_epoch"] or t["placed_at"]["epoch"])
        except Exception as e:
            t.setdefault("errors", []).append(f"{stamp()['utc']} trades unavailable: {e}")
            trades = []
        row = board_rows.get(t["slug"]) or {}
        apply_fills(t, trades, row.get("yes_book"))
        write_json(ticket_path(t["id"]), t)
        done.append(t)
    return done

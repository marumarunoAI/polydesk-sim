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


def ticket_dir(is_test=False):
    """測試單放 tickets/test/，與績效、風控用的 tickets/*.json 分開（glob 不會遞迴進去）。"""
    d = os.path.join(DIRS["tickets"], "test") if is_test else DIRS["tickets"]
    os.makedirs(d, exist_ok=True)
    return d


def ticket_path(tid, is_test=False):
    return os.path.join(ticket_dir(is_test), f"{tid}.json")


def trade_key(tr):
    return f"{tr.get('transaction_hash')}|{tr.get('token_id')}|{tr['price']}|{tr['size']}|{tr['side']}"


def book_side_for(outcome, yes_book):
    """回傳買 outcome 時「賣方」檔位 [(price, size)]（由便宜到貴）與「同側買方」檔位。"""
    bids = [(l["price"], l["size"]) for l in yes_book.get("bids_top5") or []]
    asks = [(l["price"], l["size"]) for l in yes_book.get("asks_top5") or []]
    if outcome == "YES":
        return sorted(asks), bids
    no_asks = sorted((round(1 - p, 6), s) for p, s in bids)
    no_bids = [(round(1 - p, 6), s) for p, s in asks]
    return no_asks, no_bids


def place(tid, strategy, market, outcome, limit, shares, usd, yes_book,
          is_test=False, cancel_at_epoch=None):
    """建立 ticket（冪等：同 id 已存在就不重建）。is_test=True 的單不計入績效與風控。"""
    p = ticket_path(tid, is_test)
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
        "cancel_at_epoch": cancel_at_epoch or end.timestamp() - CANCEL_BEFORE_H.get(strategy, 0) * 3600,
        "is_test": bool(is_test), "seen_trades": {},
        "queue_ahead": queue, "initial_queue": queue, "status": "open", "filled_shares": 0.0,
        "fill_cost": 0.0, "fee_paid": 0.0, "fee_rate_maker": fees.MAKER_FEE_RATE,
        "last_checked_epoch": None, "fills": [],
    }
    write_json(p, t)
    return t, True


def fetch_trades(condition_id, since_epoch, max_pages=10):
    """某 condition 在 since_epoch 之後的 taker 成交（新到舊翻頁）。
    翻頁時 cursor 不含 condition 篩選，必須每頁都重送 condition，否則會拿到別的市場的成交。"""
    out, cur = [], None
    for _ in range(max_pages):
        params = {"condition": condition_id, "limit": 500, "taker_only": "true"}
        if cur:
            params["cursor"] = cur
        d = get_json(DATA_API, params=params)
        rows = [r for r in d.get("data") or [] if r.get("condition_id") == condition_id]
        out += [r for r in rows if r["timestamp"] > since_epoch]
        cur = (d.get("pagination") or {}).get("next_cursor")
        raw_rows = d.get("data") or []
        if not raw_rows or raw_rows[-1]["timestamp"] <= since_epoch or not cur:
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
    placed = t["placed_at"]["epoch"]
    L = t["limit_price"]
    remaining = t["shares"] - t["filled_shares"]
    through = at = 0.0
    # 成交紀錄 API 有索引延遲：每次都從掛單時間重看，用 seen_trades 去重（避免漏掉晚到的成交）
    batch = {}
    for tr in trades:
        if tr["timestamp"] <= placed or tr["timestamp"] > t["cancel_at_epoch"]:
            continue  # 掛單前、或撤單時間之後的成交都與我們無關
        batch[trade_key(tr)] = batch.get(trade_key(tr), 0) + 1
    seen = t.setdefault("seen_trades", {})
    new_counts = {}
    for k, n in batch.items():
        if n > seen.get(k, 0):
            new_counts[k] = n - seen.get(k, 0)
            seen[k] = n
    for tr in trades:
        k = trade_key(tr)
        if tr["timestamp"] <= placed or tr["timestamp"] > t["cancel_at_epoch"] or new_counts.get(k, 0) <= 0:
            continue
        new_counts[k] -= 1
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
    # 簿深穿價：同一批可見流動性只算一次（crossed_claimed 記已認領量；穿價消失就歸零）。
    # 與成交紀錄可能是同一筆流動性，保守取兩者較大值而非相加。
    visible = sum(s for px, s in sellers if px <= L + 1e-9)
    claimed = t.get("crossed_claimed", 0.0)
    crossed = max(0.0, visible - claimed)
    t["crossed_claimed"] = visible
    trade_ev = through + at_ours
    got = min(remaining, max(trade_ev, crossed))
    if got > 0:
        t["fills"].append({"at": stamp(now), "shares": round(got, 4), "price": L,
                           "basis": {"trades_through": through, "trades_at_limit_after_queue": at_ours,
                                     "book_crossed_depth": crossed}})
        t["crossed_claimed"] = max(t["crossed_claimed"], 0.0)
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
    """對每張未完成 ticket 用真實成交 + 目前訂單簿判定成交。board_rows: {slug: row}。
    成交紀錄 API 失敗 → 這張單本輪完全不更新（不推進 last_checked_epoch、不撤單），下輪再補。"""
    done = []
    for t in open_tickets():
        try:
            trades = fetch_trades(t["condition_id"], (t["last_checked_epoch"] or t["placed_at"]["epoch"]) - 900)
        except Exception as e:
            t.setdefault("errors", []).append(f"{stamp()['utc']} trades unavailable: {e}")
            write_json(ticket_path(t["id"]), t)
            continue
        row = board_rows.get(t["slug"]) or {}
        apply_fills(t, trades, row.get("yes_book"))
        write_json(ticket_path(t["id"]), t)
        done.append(t)
    return done

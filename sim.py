"""sim.py — 模擬 maker 限價單（tickets/）與成交判定。不簽名、不送單。

成交規則（不假設以 mid 成交，只掛 maker / post-only）：
  建立時若限價會穿過或碰到對手最佳價（買單 L ≥ best ask；賣單經鏡像後同樣判斷），
  一律拒單 rejected_post_only：不成交、不改用 taker、不記手續費、不自動改價。
  掛單後訂單簿變動使對手價穿過我們限價，不算成交、也不因此拒單；只認真實成交紀錄。
  我們掛「買 outcome O、限價 L」的 maker 單，只有真實市場有人賣給這個價位才算成交：
    掛單後的真實成交（Polymarket Data API /v2/trades，taker 側）：
    taker 賣 O、或 taker 買另一邊（價格換算 1−p），換算價 px：
      px < L  → 整筆量可成交給我們；
      px == L → 先扣掉掛單時同價位排在我們前面的量（queue_ahead），剩下的才給我們。
  成交量上限為剩餘股數，所以可能部分成交。maker 手續費依官方文件 = 0。
  成交紀錄 API 有延遲：一般輪詢重疊視窗 TRADE_LOOKBACK_SEC；撤單／結算前從掛單時間重抓再判定。"""
import glob
import os

from common import DIRS, get_json, now_utc, parse_iso, read_json, stamp, write_json
import fees

DATA_API = "https://data-api.polymarket.com/v2/trades"
# Data API 成交紀錄延遲實測中位 457 秒、最大 954 秒；一般輪詢重疊至少 1000 秒。
TRADE_LOOKBACK_SEC = 1200
TERMINAL = ("filled", "cancelled", "partial_cancelled", "rejected_post_only", "settled")
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
    yes_book = yes_book or {}
    bids = [(l["price"], l["size"]) for l in yes_book.get("bids_top5") or []]
    asks = [(l["price"], l["size"]) for l in yes_book.get("asks_top5") or []]
    if outcome == "YES":
        return sorted(asks), bids
    no_asks = sorted((round(1 - p, 6), s) for p, s in bids)
    no_bids = [(round(1 - p, 6), s) for p, s in asks]
    return no_asks, no_bids


def _present(x):
    return x not in (None, "unavailable", "")


def best_bid_ask(outcome, yes_book):
    """該 outcome 的最佳買／賣價。優先用 yes_book 的 best_*，否則用檔位。"""
    yes_book = yes_book or {}
    bb, ba = yes_book.get("best_bid"), yes_book.get("best_ask")
    if outcome == "YES":
        bid, ask = (bb if _present(bb) else None), (ba if _present(ba) else None)
    else:
        bid = round(1 - ba, 6) if _present(ba) else None
        ask = round(1 - bb, 6) if _present(bb) else None
    if bid is None or ask is None:
        sellers, same = book_side_for(outcome, yes_book)
        if ask is None and sellers:
            ask = sellers[0][0]
        if bid is None and same:
            bid = max(px for px, _s in same)
    return bid, ask


def would_cross_book(outcome, limit, yes_book):
    """買單限價 ≥ 對手最佳賣價（穿過或碰到）則 post-only 應拒。回傳 (crosses, best_bid, best_ask)。"""
    bid, ask = best_bid_ask(outcome, yes_book)
    crosses = ask is not None and limit + 1e-9 >= ask
    return crosses, bid, ask


def place(tid, strategy, market, outcome, limit, shares, usd, yes_book,
          is_test=False, cancel_at_epoch=None, extra=None):
    """建立 ticket（冪等：同 id 已存在就不重建）。is_test=True 的單不計入績效與風控。"""
    p = ticket_path(tid, is_test)
    if os.path.exists(p):
        return read_json(p), False
    _, same = book_side_for(outcome, yes_book)
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
        "fee_source": fees.fee_source(), "maker_rebate_rate": fees.maker_rebate_rate(),
        "last_checked_epoch": None, "fills": [],
    }
    t.update(extra or {})
    crosses, bid, ask = would_cross_book(outcome, limit, yes_book)
    if crosses:
        # post-only：建立時穿價／碰到對手價就拒單。不改價、不吃單、不記手續費。
        t["status"] = "rejected_post_only"
        t["reject_reason"] = (
            f"rejected_post_only: buy {outcome} limit {limit} >= best ask {ask}")
        t["reject_best_bid"] = bid
        t["reject_best_ask"] = ask
        t["fee_paid"] = 0.0
        t["filled_shares"] = 0.0
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


def apply_fills(t, trades, yes_book=None, now=None):
    """純函式：只依真實成交紀錄更新 ticket（可單元測試）。
    yes_book 保留給呼叫端相容，不用來判定成交或拒單（掛單後簿面變動不算成交依據）。"""
    now = now or now_utc()
    if t["status"] in TERMINAL:
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
    got = min(remaining, through + at_ours)
    if got > 0:
        t["fills"].append({"at": stamp(now), "shares": round(got, 4), "price": L,
                           "basis": {"trades_through": through, "trades_at_limit_after_queue": at_ours}})
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


def fetch_since_epoch(t, now=None, force_from_placed=False):
    """一律從掛單時間抓起，覆蓋整段掛單生命期（含遲到的成交紀錄）。
    force_from_placed 保留給呼叫端語意（結算／撤單前強制重掃），回傳值相同。"""
    return t["placed_at"]["epoch"]


def rescan_ticket(t, yes_book=None, now=None, force_from_placed=False):
    """抓成交並套用 apply_fills。API 失敗則不更新（不推進 last_checked、不撤單）。
    回傳 (ticket, ok)。yes_book 只為相容保留，不影響成交判定。"""
    now = now or now_utc()
    if t["status"] in TERMINAL:
        return t, True
    try:
        since = fetch_since_epoch(t, now, force_from_placed=force_from_placed)
        trades = fetch_trades(t["condition_id"], since)
    except Exception as e:
        t.setdefault("errors", []).append(f"{stamp()['utc']} trades unavailable: {e}")
        return t, False
    apply_fills(t, trades, yes_book, now=now)
    return t, True


def rescan_before_settle(t, now=None):
    """結算（或到期判定未成交）前，強制從掛單時間重抓一次成交再判定。
    若先前已因到期標成 cancelled／partial_cancelled，先暫時重新打開，讓遲到、
    但時間戳仍在掛單～撤單窗口內的成交能補上；抓取失敗則恢復原狀態、不更新。"""
    now = now or now_utc()
    if t["status"] in ("rejected_post_only", "settled", "filled"):
        return t, True
    prev = t["status"]
    if t["status"] in ("cancelled", "partial_cancelled"):
        t["status"] = "partial" if t["filled_shares"] > 0 else "open"
    t2, ok = rescan_ticket(t, None, now=now, force_from_placed=True)
    if not ok:
        t2["status"] = prev
        return t2, False
    return t2, True


def check_all(board_rows):
    """對每張未完成 ticket 用真實成交判定。board_rows: {slug: row}（簿面不作為成交依據）。
    即將到撤單／到期時改從掛單時間重抓。成交紀錄 API 失敗 → 本輪完全不更新。"""
    done = []
    now = now_utc()
    for t in open_tickets():
        expiring = now.timestamp() >= t["cancel_at_epoch"]
        t, ok = rescan_ticket(t, (board_rows.get(t["slug"]) or {}).get("yes_book"),
                              now=now, force_from_placed=expiring)
        write_json(ticket_path(t["id"]), t)
        if ok:
            done.append(t)
    return done


# ---------- 中途出場（maker 賣單，鏡像成交） ----------
def exit_id(parent_id):
    return f"{parent_id}_EXIT"


def read_exit(parent_id):
    p = ticket_path(exit_id(parent_id))
    return read_json(p) if os.path.exists(p) else None


def exit_proceeds(x):
    """出場單已成交部分的收入（鏡像買單成本換算回賣出收入）。"""
    return x["filled_shares"] - x["fill_cost"]


def place_exit(parent, market, yes_book, reason, now=None):
    """對已成交部位掛 maker 賣單（不假設以 mid 成交）。

    賣出 outcome O @ S，在統一訂單簿裡等同「買相反 outcome @ 1−S」的 maker 買單，成交判定因此
    完全重用 apply_fills（真實 taker 成交穿過/等於限價＋排隊）。
    掛價：自家這一側最佳賣價 − 1 tick（不碰最佳買價）；價差只有 1 tick 就掛在最佳賣價排隊。
    若掛價會穿價，place() 回傳 rejected_post_only，不自動改價。
    回傳 (exit_ticket, created)。"""
    held = parent["filled_shares"]
    if held <= 0:
        raise ValueError("no filled position to exit")
    yb = market["yes_book"]
    tick = float(market["tick_size"]) if market.get("tick_size") not in (None, "unavailable") else 0.01
    if parent["outcome"] == "YES":
        bid, ask = yb["best_bid"], yb["best_ask"]
    else:
        bid = 1 - yb["best_ask"] if yb["best_ask"] != "unavailable" else "unavailable"
        ask = 1 - yb["best_bid"] if yb["best_bid"] != "unavailable" else "unavailable"
    if "unavailable" in (bid, ask):
        raise ValueError("one-sided book: cannot price a maker exit")
    sell = ask - tick if ask - tick > bid + 1e-9 else ask
    sell = round(round(sell / tick) * tick, 6)
    mirror_outcome = "NO" if parent["outcome"] == "YES" else "YES"
    mirror_limit = round(1 - sell, 6)
    # 賣單不得先被當成吃單：place() 若穿價會以 rejected_post_only 拒單，不改價
    t, created = place(exit_id(parent["id"]), parent["strategy"], market, mirror_outcome, mirror_limit,
                       held, round(held * mirror_limit, 2), yb,
                       cancel_at_epoch=parse_iso(market["end_utc"]).timestamp(),
                       extra={"is_exit": True, "exit_of": parent["id"], "exit_reason": reason,
                              "sell_outcome": parent["outcome"], "sell_price": sell,
                              "order_type": "maker_limit_sell (simulated, mirrored as opposite-side buy)"})
    return t, created


def cancel_entry_remainder(parent):
    """出場訊號出現時，撤掉進場單還沒成交的部分。"""
    if parent["status"] in ("open", "partial"):
        parent["status"] = "cancelled" if parent["filled_shares"] == 0 else "partial_cancelled"
        write_json(ticket_path(parent["id"]), parent)
    return parent

"""blind.py — 把掃到的市場寫成 blind/<slug>.json：只有規則、關卡、到期、結算來源。
不含任何價格、成交量、流動性。Quant 只讀這個資料夾。"""
import glob
import os

from common import DIRS, read_json, stamp, write_json

ALLOWED = ("slug", "market_id", "condition_id", "question", "kind", "asset",
           "direction", "level", "rules", "resolution_source", "end_utc",
           "end_taipei", "event_slug", "event_title", "yes_token", "no_token",
           "tick_size", "min_order_size", "tags")
PRICE_WORDS = ("price", "bid", "ask", "mid", "volume", "liquidity", "spread",
               "book", "outcomeprices", "last_trade")


def to_blind(market):
    b = {k: market[k] for k in ALLOWED if k in market}
    for k in b:
        assert not any(w in k.lower() for w in PRICE_WORDS), k
    return b


def write_blind(markets):
    ts = stamp()
    for m in markets:
        b = to_blind(m)
        b["written_at"] = ts
        write_json(os.path.join(DIRS["blind"], f"{m['slug']}.json"), b)
    return len(markets)


def load_blind():
    """Quant 唯一的輸入來源。"""
    return [read_json(p) for p in sorted(glob.glob(os.path.join(DIRS["blind"], "*.json")))]

"""journal.py — journal/journal.csv，每筆預測一列（有沒有交易都記）。
鍵 = (date_taipei, strategy, market_slug)：同日重跑不重複記。"""
import csv
import os

from common import DIRS

COLUMNS = ["time_taipei", "time_utc", "date_taipei", "strategy", "market_slug",
           "asset", "kind", "side", "fair", "entry_mid", "edge", "threshold",
           "decision", "reason", "size", "limit_price", "fee", "fill_status",
           "filled_shares", "ticket_id", "result", "brier_desk", "brier_market",
           "pnl", "settled_date_taipei", "mirror"]


def path():
    return os.path.join(DIRS["journal"], "journal.csv")


def load():
    if not os.path.exists(path()):
        return []
    with open(path(), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(rows):
    os.makedirs(DIRS["journal"], exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    os.replace(tmp, path())


def key(r):
    return (r["date_taipei"], r["strategy"], r["market_slug"])


def add(new_rows):
    """只新增沒出現過的鍵，回傳實際新增數。"""
    rows = load()
    seen = {key(r) for r in rows}
    added = [r for r in new_rows if key(r) not in seen]
    if added:
        save(rows + added)
    return len(added)


def has(day, strategy, slug):
    return any(key(r) == (day, strategy, slug) for r in load())

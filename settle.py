"""settle.py — 結算回填：用 Gamma 已結算結果回填 journal 的 result、brier_desk、
brier_market，以及 tickets 的虛擬損益。"""
import glob
import json
import os

from common import DIRS, get_json, now_utc, parse_iso, read_json, today_tpe, write_json
import journal
import sim

GAMMA = "https://gamma-api.polymarket.com/markets"


def resolution(slug):
    """回傳 1（YES）、0（NO）或 None（未結算／無法判定）。"""
    rows = get_json(GAMMA, params={"slug": slug})
    if not rows:
        rows = get_json(GAMMA, params={"slug": slug, "closed": "true"})
    if not rows:
        return None
    m = rows[0]
    if not m.get("closed") or m.get("umaResolutionStatus") not in (None, "resolved"):
        return None
    try:
        prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        outcomes = [o.lower() for o in json.loads(m.get("outcomes") or "[]")]
    except ValueError:
        return None
    if sorted(prices) != [0.0, 1.0]:
        return None
    return 1 if prices[outcomes.index("yes")] == 1.0 else 0


def run():
    rows = journal.load()
    now = now_utc()
    pending = []
    for slug in sorted({r["market_slug"] for r in rows if r["result"] == ""}):
        fp = os.path.join(DIRS["fair"], f"{slug}.json")
        if os.path.exists(fp) and parse_iso(read_json(fp)["end_utc"]) > now:
            continue  # 還沒到期，不必查
        pending.append(slug)
    res = {}
    for slug in pending:
        try:
            res[slug] = resolution(slug)
        except Exception:
            res[slug] = None
    day = today_tpe()
    tickets = {}
    for p in glob.glob(os.path.join(DIRS["tickets"], "*.json")):
        t = read_json(p)
        tickets[t["id"]] = t
    n = 0
    for r in rows:
        y = res.get(r["market_slug"])
        if r["result"] != "" or y is None:
            continue
        r["result"] = y
        r["brier_desk"] = round((float(r["fair"]) - y) ** 2, 6) if r["fair"] not in ("", "unavailable") else "unavailable"
        r["brier_market"] = round((float(r["entry_mid"]) - y) ** 2, 6) if r["entry_mid"] not in ("", "unavailable") else "unavailable"
        r["settled_date_taipei"] = day
        t = tickets.get(r["ticket_id"])
        if t:
            won = (y == 1) == (t["outcome"] == "YES")
            x = tickets.get(sim.exit_id(t["id"]))  # 中途出場：已賣出部分按出場收入，其餘持有到結算
            sold = x["filled_shares"] if x else 0.0
            proceeds = sim.exit_proceeds(x) if x else 0.0
            held = t["filled_shares"] - sold
            pnl = proceeds + held * (1.0 if won else 0.0) - t["fill_cost"] - t["fee_paid"] \
                - (x["fee_paid"] if x else 0.0)
            t["exited_shares"] = sold
            t["status"] = "settled"
            t["result"] = y
            t["pnl"] = round(pnl, 4)
            t["settled_date_taipei"] = day
            write_json(os.path.join(DIRS["tickets"], f"{t['id']}.json"), t)
            r["pnl"] = round(pnl, 4)
            r["fill_status"] = "settled"
        n += 1
    journal.save(rows)
    return n


if __name__ == "__main__":
    print(f"settled rows: {run()}")

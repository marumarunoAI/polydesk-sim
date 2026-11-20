"""exits.py — 中途出場（DESK_RULES：邊際 < 0.5pp、到期前 24 小時；S2 出現否決條件也要出場）。

觸發條件（對每張已有成交股數、尚未結算的進場單）：
  S1/S2：距到期 ≤ 24 小時
  S1/S2/S3：目前邊際 < 0.5pp（持有那一側：fair_side − mid_side）
  S2：否決條件現在成立（窗口內有 FOMC、資金費率極端、關卡附近有大額清算叢集）
  S3：持有到中午結算，不適用 24 小時規則
輸入缺（fair/mid unavailable）→ 本輪不評估邊際（時間規則照常），不當成出場理由。

出場做法（寫明所選做法）：掛 **maker 賣單**，掛在自家這一側最佳賣價 −1 tick，之後用真實成交／訂單簿深度判定
成交（sim.place_exit，鏡像成「買相反 outcome」重用 apply_fills）。**不假設以 mid 成交**，也不吃單。
出場單掛到市場到期；到期仍沒成交的部分持有到結算。出場紀錄寫 journal/exits.csv（以 ticket id 去重）。"""
import csv
import glob
import os

from common import DIRS, UNAVAILABLE, now_utc, parse_iso, read_json, stamp
import sim
import strategies as st

EDGE_EXIT = 0.005
EXIT_WINDOW_H = 24
COLUMNS = ["time_taipei", "time_utc", "parent_ticket", "strategy", "slug", "outcome",
           "held_shares", "reason", "sell_limit", "exit_ticket"]


def margin_for(parent, fair, row):
    q, mid = fair.get("fair_yes"), row["yes_book"].get("mid")
    if q in (None, UNAVAILABLE) or mid in (None, UNAVAILABLE):
        return None
    return (q - mid) if parent["outcome"] == "YES" else (mid - q)


def exit_reason(parent, fair, row, ev, now=None):
    now = now or now_utc()
    s = parent["strategy"]
    hours = (parse_iso(parent["end_utc"]) - now).total_seconds() / 3600
    if s in ("S1", "S2") and hours <= EXIT_WINDOW_H:
        return f"within {EXIT_WINDOW_H}h of expiry ({hours:.1f}h left)"
    m = margin_for(parent, fair, row)
    if m is not None and m < EDGE_EXIT:
        return f"edge {m * 100:.2f}pp < 0.5pp"
    if s == "S2":
        if fair.get("fomc_in_window") is True:
            return "S2 veto appeared: FOMC inside window"
        ea = (ev or {}).get("assets", {}).get(parent["asset"])
        if ea:
            clusters, _ = st.liq_clusters_value(ea)
            if clusters != UNAVAILABLE and st.liq_near(clusters, row["level"]) >= st.LIQ_CLUSTER_MIN_USD:
                return "S2 veto appeared: liquidation cluster near strike"
            f8, src = st._funding_8h(ea)
            if f8 != UNAVAILABLE and abs(f8) >= st.FUNDING_EXTREME_8H:
                return f"S2 veto appeared: extreme funding {f8:.6f}/8h ({src})"
    return None


def _log_exit(parent, exit_t, reason):
    path = os.path.join(DIRS["journal"], "exits.csv")
    new = not os.path.exists(path)
    os.makedirs(DIRS["journal"], exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow({"time_taipei": stamp()["taipei"], "time_utc": stamp()["utc"],
                    "parent_ticket": parent["id"], "strategy": parent["strategy"], "slug": parent["slug"],
                    "outcome": parent["outcome"], "held_shares": parent["filled_shares"], "reason": reason,
                    "sell_limit": exit_t["sell_price"], "exit_ticket": exit_t["id"]})


def run(rows, fairs, ev, now=None):
    """掃描所有進場單，依條件掛出場單。回傳 [(parent_id, reason, status)]。冪等：同一張單只會出場一次。"""
    now = now or now_utc()
    out = []
    for p in sorted(glob.glob(os.path.join(DIRS["tickets"], "*.json"))):
        t = read_json(p)
        if t.get("is_exit") or t["status"] == "settled" or t["filled_shares"] <= 0:
            continue
        if sim.read_exit(t["id"]):
            continue
        row, fair = rows.get(t["slug"]), fairs.get(t["slug"])
        if not row or not fair:
            out.append((t["id"], "not in today's scan: exit not evaluated", "skipped"))
            continue
        reason = exit_reason(t, fair, row, ev, now)
        if not reason:
            continue
        sim.cancel_entry_remainder(t)
        try:
            x, created = sim.place_exit(t, row, row["yes_book"], reason, now)
        except ValueError as e:
            out.append((t["id"], reason, f"exit not placed: {e}"))
            continue
        if created:
            _log_exit(t, x, reason)
        out.append((t["id"], reason, "exit placed @%s" % x["sell_price"]))
    return out

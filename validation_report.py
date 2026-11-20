"""validation_report.py — 由 validate_fills.py 呼叫：把測試單、期間真實成交與模擬判斷寫成報告。"""
import json
import os

import sim
from common import ROOT, iso_tpe, now_utc, read_json, stamp
from datetime import datetime, timezone

BOUND_TOL = 1e-6


def _tp(epoch):
    return iso_tpe(datetime.fromtimestamp(epoch, timezone.utc))[5:19].replace("T", " ")


def oracle(t, trades):
    """獨立重算（不用 sim.apply_fills）：掛單後的真實 taker 成交對這張買單的上下界。
    upper：排隊量為 0；lower：排隊量永不離開（沒人撤單）。僅看成交紀錄，不含訂單簿穿價。"""
    placed = t["placed_at"]["epoch"]
    through = at = 0.0
    for tr in trades:
        if tr["timestamp"] <= placed:
            continue
        px = sim.trade_px_for(t["outcome"], tr)
        if px is None:
            continue
        if px < t["limit_price"] - 1e-9:
            through += float(tr["size"])
        elif abs(px - t["limit_price"]) < 1e-9:
            at += float(tr["size"])
    q0 = t.get("initial_queue", t["queue_ahead"])
    upper = min(t["shares"], through + at)
    lower = min(t["shares"], through + max(0.0, at - q0))
    return {"through": through, "at": at, "upper": upper, "lower": lower, "q0": q0}


def crossing_polls(t, series):
    """輪詢中對手最佳賣價 ≤ 我們限價的次數（訂單簿穿價證據）。"""
    n = 0
    for x in series:
        if t["outcome"] == "YES":
            ask = x["ask"]
        else:
            ask = 1 - x["bid"] if x["bid"] != "unavailable" else "unavailable"
        if ask != "unavailable" and ask <= t["limit_price"] + 1e-9:
            n += 1
    return n


def verdict(t, o, series=()):
    """只比對獨立成交上下界：filled 必須落在 [lower, upper]。超出即不合理。
    series 保留相容，不再把訂單簿穿價算進上界。"""
    f = t["filled_shares"]
    notes = []
    ok = True
    if t.get("status") == "rejected_post_only":
        if f > BOUND_TOL or t.get("fee_paid", 0) > BOUND_TOL:
            ok = False
            notes.append("post-only 拒單卻有成交或手續費")
        else:
            notes.append(t.get("reject_reason") or "rejected_post_only")
        return ok, notes
    if f < o["lower"] - BOUND_TOL:
        ok = False
        notes.append(f"模擬成交 {f:g} < 下界 {o['lower']:g}（漏成交？）")
    if f > o["upper"] + BOUND_TOL:
        ok = False
        notes.append(f"模擬成交 {f:g} > 上界 {o['upper']:g}（多算？）")
    if f == 0 and o["upper"] == 0 and ok:
        notes.append("期間沒有任何能成交的真實成交 → 不成交，合理")
    return ok, notes


def reset_ticket_for_replay(t):
    """清掉舊模擬成交（含已刪除的 book_crossed_depth 認領），保留掛單價、排隊與期間。"""
    t = json.loads(json.dumps(t))
    t["filled_shares"] = 0.0
    t["fill_cost"] = 0.0
    t["fee_paid"] = 0.0
    t["fills"] = []
    t["seen_trades"] = {}
    t.pop("crossed_claimed", None)
    t["queue_ahead"] = t.get("initial_queue", t.get("queue_ahead", 0))
    t["status"] = "open"
    t["last_checked_epoch"] = None
    return t


def _raw_by_key(raw_trades):
    """把 raw 的 trades（list of {trade, first_seen, n} 或 key→rec）編成 condition → key → rec。"""
    out = {}
    for c, rows in raw_trades.items():
        if isinstance(rows, dict):
            items = rows.values()
        else:
            items = rows
        d = {}
        for r in items:
            tr = r["trade"] if isinstance(r, dict) and "trade" in r else r
            k = sim.trade_key(tr)
            rec = d.setdefault(k, {"trade": tr, "first_seen": r.get("first_seen", tr["timestamp"]) if isinstance(r, dict) else tr["timestamp"], "n": 0})
            n = r.get("n", 1) if isinstance(r, dict) else 1
            rec["n"] = max(rec["n"], n)
        out[c] = d
    return out


def replay(state, mkts, tickets, raw_trades, series, end_now=None):
    """用已錄下的真實成交，以現行 apply_fills（只認 trades）重算測試單並寫報告。不打 API。"""
    raw = _raw_by_key(raw_trades)
    if end_now is None:
        end_now = datetime.fromtimestamp(state["planned_end"]["epoch"], timezone.utc)
    replayed = []
    for t0 in tickets:
        t = reset_ticket_for_replay(t0)
        recs = raw.get(t["condition_id"], {})
        trades = [r["trade"] for r in recs.values() for _ in range(r["n"])]
        sim.apply_fills(t, trades, {}, now=end_now)
        replayed.append(t)
    tids = [t["id"] for t in replayed]
    write(state, mkts, tids, raw, series, tickets=replayed, correction=True)
    return replayed


def write(state, mkts, tids, raw, series, tickets=None, correction=False):
    tickets = tickets or [read_json(sim.ticket_path(i, True)) for i in tids]
    cond_trades = {c: [r["trade"] for r in v.values() for _ in range(r["n"])] for c, v in raw.items()}
    lag = []
    for c, v in raw.items():
        for r in v.values():
            lag.append(r["first_seen"] - r["trade"]["timestamp"])
    lag.sort()
    lines = ["# 真實資料成交模擬驗證報告", "",
             f"- 產生時間：{stamp()['taipei']}（台北）／{stamp()['utc']}",
             f"- 驗證期間：{state['started']['taipei']} → 預計結束 {state['planned_end']['taipei']}（台北），每 ~60 秒輪詢一次",
             "- 性質：純模擬。測試單（`is_test=true`，放 `tickets/test/`）不進 journal、績效與風控；沒有任何簽名或送單，只讀公開 API。",
             "- 判斷程式：`sim.apply_fills()`（只認 Data API `/v2/trades`；建立時穿價為 `rejected_post_only`）。獨立檢查用 `validation_report.oracle()`（只看掛單後的真實成交，算上下界）。「合理？」欄直接比對模擬成交與上下界，超出即標不合理。",
             "", "## 規則更正", "",
             "- 舊版 `sim.apply_fills` 把訂單簿穿價深度（`book_crossed_depth`）當作成交依據，過於樂觀；舊報告的「合理？」把這段深度加進上界，因此會把超出成交紀錄上下界的模擬成交標成合理。",
             "- 舊結論「全部落在上下界內」有誤。典型例子：`will-ethereum-reach-1800-on-november-20-2026` 四張 YES 測試單，獨立上下界為 0/0，舊模擬卻判 10/10 成交（全部來自簿深穿價），期間沒有能成交的真實 taker 紀錄（僅見一筆 Yes BUY，不構成 YES 買單成交）。",
             "- 現行規則：建立時限價穿過或碰到對手最佳價 → 直接拒單，不成交、不改用 taker、不記手續費、不自動改價。掛單後簿面變動不作為成交或拒單依據，只認真實成交（穿過限價，或同價且扣完排隊量）。撤單／結算前從掛單時間再抓一次成交。",
             "", "## 市場", ""]
    for s, m in mkts.items():
        n = len(cond_trades[m["condition_id"]])
        lines.append(f"- `{s}`：{m['question']}（驗證期間觀察到 {n} 筆 taker 成交）")
    lines += ["", "## 掛單與結果", "",
              "| 市場 | 案例 | 方向@限價 | 掛單時排隊量 | 期間可成交量上界/下界 | 模擬成交 | 狀態 | 合理？ |",
              "|---|---|---|---|---|---|---|---|"]
    problems, all_ok = [], True
    for t in tickets:
        o = oracle(t, cond_trades[t["condition_id"]])
        ok, notes = verdict(t, o, series[t['slug']])
        all_ok &= ok
        short = t["slug"][:38]
        lines.append(f"| {short} | {t['case']} | {t['outcome']}@{t['limit_price']} | {o['q0']:g} | "
                     f"{o['upper']:g} / {o['lower']:g}（穿過 {o['through']:g}，同價 {o['at']:g}） | "
                     f"{t['filled_shares']:g}/{t['shares']:g} | {t['status']} | {'是' if ok else '否'} {'；'.join(notes)} |")
        if not ok:
            problems.append(f"{t['slug']} {t['case']}: {'；'.join(notes)}")
    lines += ["", "## 成交明細（模擬判斷）", ""]
    any_fill = False
    for t in tickets:
        for f in t["fills"]:
            any_fill = True
            lines.append(f"- {_tp(f['at']['epoch'])} 台北 `{t['case']}` {t['outcome']}@{t['limit_price']} "
                         f"+{f['shares']:g} 股，依據 {f['basis']}")
    if not any_fill:
        lines.append("- 整段期間沒有任何模擬成交。")
    lines += ["", "## 期間真實成交（taker 側，節錄每市場最近 15 筆）", ""]
    for s, m in mkts.items():
        trs = sorted(cond_trades[m["condition_id"]], key=lambda x: x["timestamp"])
        lines.append(f"**{s}**（共 {len(trs)} 筆）")
        lines.append("")
        lines.append("| 台北時間 | outcome | side | price | size |")
        lines.append("|---|---|---|---|---|")
        for tr in trs[-15:]:
            lines.append(f"| {_tp(tr['timestamp'])} | {tr['outcome']} | {tr['side']} | {tr['price']} | {tr['size']} |")
        lines.append("")
    # 額外檢查
    touched = []
    for t in tickets:
        sr = series[t["slug"]]
        if t["outcome"] == "YES":
            hit = [x for x in sr if x["mid"] != "unavailable" and x["mid"] <= t["limit_price"] + 1e-9]
        else:
            hit = [x for x in sr if x["mid"] != "unavailable" and 1 - x["mid"] <= t["limit_price"] + 1e-9]
        if hit and t["filled_shares"] == 0:
            touched.append((t, len(hit)))
    lines += ["## 額外檢查", ""]
    if lag:
        med = lag[len(lag) // 2]
        late = sum(1 for x in lag if x > 120)
        lines.append(f"- 成交紀錄 API 延遲（首次看到時間 − 成交時間戳）：中位數 {med:.0f} 秒，最大 {lag[-1]:.0f} 秒，"
                     f">120 秒者 {late}/{len(lag)} 筆。`sim.apply_fills` 每次從掛單時間重掃並以交易鍵去重，所以晚到的成交不會漏。")
    lines.append(f"- 「mid 碰到限價但沒有真實賣單成交」的測試單：{len(touched)} 張"
                 + ("（" + "、".join(f"{t['case']}×{n}次輪詢" for t, n in touched) + "）→ 模擬正確地沒有成交，mid 觸及不算成交。" if touched else "。"))
    lines.append("- 排隊量的假設：同價位只在有真實成交消耗時才前進，不計撤單，所以 `at_bid` 類案例偏保守。")
    xs = [(t, crossing_polls(t, series[t["slug"]])) for t in tickets]
    crossed_seen = [(t, n) for t, n in xs if n > 0]
    book_only = [t for t in tickets if t["filled_shares"] == 0 and crossing_polls(t, series[t["slug"]]) > 0]
    lines.append("- 訂單簿穿價不再是成交依據。輪詢中曾看到對手價穿過限價的測試單："
                 + ("、".join(f"{t['case']}×{n}" for t, n in crossed_seen) if crossed_seen else "無")
                 + "；其中無真實成交、模擬也不成交者 "
                 + ("、".join(t["case"] for t in book_only) if book_only else "無")
                 + "。")
    lines += ["", "## 結論與發現的問題", ""]
    lines.append(f"- 全部 {len(tickets)} 張測試單的模擬成交都落在獨立計算的上下界內：**{'是' if all_ok else '否'}**。")
    for p in problems:
        lines.append(f"- 問題：{p}")
    if all_ok:
        lines.append("- 沒有發現成交判斷錯誤。限制：樣本僅限本次驗證的幾個市場與時段；成交量大的市場才有足夠的對照。")
    lines.append("- 已知限制：Data API 回報的是 taker 成交，無法看到 maker 端的撤單，排隊位置只能估；成交時間戳為秒級。")
    with open(os.path.join(ROOT, "docs", "fill_validation.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    raw_out = {"series": series, "trades": {c: list(v.values()) for c, v in raw.items()},
               "tickets": [{k: v for k, v in t.items() if k != "seen_trades"} for t in tickets]}
    p = os.path.join(ROOT, "docs", "fill_validation_raw.json")
    s = json.dumps(raw_out, ensure_ascii=False)
    if len(s) < 1_500_000:
        with open(p, "w", encoding="utf-8") as f:
            f.write(s)

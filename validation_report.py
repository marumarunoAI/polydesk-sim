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
    f = t["filled_shares"]
    crossed = sum(x["basis"]["book_crossed_depth"] for x in t["fills"])
    notes = []
    ok = True
    if f < o["lower"] - BOUND_TOL:
        ok = False
        notes.append(f"模擬成交 {f:g} < 下界 {o['lower']:g}（漏成交？）")
    if f > o["upper"] + min(crossed, t["shares"]) + BOUND_TOL:
        ok = False
        notes.append(f"模擬成交 {f:g} > 上界 {o['upper']:g} + 訂單簿穿價 {crossed:g}（多算？）")
    if f > o["upper"] + BOUND_TOL and crossing_polls(t, series) == 0:
        ok = False
        notes.append("成交量超過真實成交所能支持的量，且輪詢中從未看到簿子穿價（無證據）")
    if f == 0 and o["upper"] == 0:
        notes.append("期間沒有任何能成交的真實成交 → 不成交，合理")
    return ok, notes


def write(state, mkts, tids, raw, series):
    tickets = [read_json(sim.ticket_path(i, True)) for i in tids]
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
             "- 判斷程式：`sim.apply_fills()`。獨立檢查用 `validation_report.oracle()`（只看掛單後的真實成交，算上下界）。",
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
    lines.append("- 訂單簿穿價成交：只有輪詢時對手最佳賣價 ≤ 我們限價才算，數量依該檔深度，並先扣掉排在我們前面的買單量；同一批可見流動性只認領一次。")
    xs = [(t, crossing_polls(t, series[t["slug"]])) for t in tickets if any(x["basis"]["book_crossed_depth"] > 0 for x in t["fills"])]
    lines.append(f"- 以訂單簿穿價成交的測試單 {len(xs)} 張，輪詢中看到穿價的次數：" + "、".join(f"{t['case']}×{n}" for t, n in xs) + "。")
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

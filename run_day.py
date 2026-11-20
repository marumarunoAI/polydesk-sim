"""run_day.py — 一個指令跑完一天（交易員每天台北 13:30 手動執行；本程式不建定時任務）。

順序：結算回填 → 掃描 → blind/ → 盲算 fair/ → 才抓 board/、evidence/（經 gate 讀）
      → 決策 → 風控 → 掛模擬 maker 單 → 檢查先前 tickets 成交 → 寫 journal。
冪等：同一台北日重跑，fair 不重算、journal 同鍵不重記、ticket 同 id 不重建。"""
import collections
import os
import sys

from common import DIRS, UNAVAILABLE, now_utc, read_json, stamp, today_tpe
import blind
import board
import evidence
import gate
import journal
import quant
import risk_gate
import settle
import sim
import strategies as st

DECIDERS = {"S1": st.decide_s1, "S2": st.decide_s2, "S3": st.decide_s3}


def strategies_for(m, fair):
    if m["kind"] == "above":
        return ["S3"]
    out = ["S1"]
    q = fair.get("fair_yes")
    if q not in (None, UNAVAILABLE) and q <= st.FAR_STRIKE_MAX_FAIR:
        out.append("S2")
    return out


def exposure_and_pnl(rows_by_slug):
    """由 tickets 算目前曝險（已成交 + 掛單中）與當日損益（今日已實現 + 未實現按 mid）。"""
    import glob
    exp = {"by_market": collections.Counter(), "by_asset_barrier": collections.Counter()}
    day = today_tpe()
    pnl = 0.0
    for p in glob.glob(os.path.join(DIRS["tickets"], "*.json")):
        t = read_json(p)
        if t["status"] == "settled":
            if t.get("settled_date_taipei") == day:
                pnl += t.get("pnl", 0.0)
            continue
        live = t["fill_cost"] + (t["shares"] - t["filled_shares"]) * t["limit_price"] \
            if t["status"] in ("open", "partial") else t["fill_cost"]
        exp["by_market"][t["slug"]] += live
        exp["by_asset_barrier"][t["asset"]] += live
        mid = (rows_by_slug.get(t["slug"]) or {}).get("yes_book", {}).get("mid", UNAVAILABLE)
        if t["filled_shares"] > 0 and mid != UNAVAILABLE:
            m = mid if t["outcome"] == "YES" else 1 - mid
            pnl += t["filled_shares"] * m - t["fill_cost"]
    return exp, pnl


def main():
    t0 = now_utc()
    day = today_tpe(t0)
    print(f"== run_day {day}（台北）開始 {stamp(t0)['taipei']}")

    n_settled = settle.run()
    print(f"[settle] 回填結算 {n_settled} 列")

    markets, stats = board.scan_markets()           # Gamma：只取規則與中繼資料
    blind.write_blind(markets)
    print(f"[scan] events={stats['events']} 排除短線={stats['excluded_short']} "
          f"排除體育/選舉/政治={stats['excluded_banned']} → 市場 {len(markets)}")

    n_fair = quant.run(blind.load_blind())           # 只讀 blind/
    print(f"[quant] 新寫 fair {n_fair} 筆（今日已存在者保留）")

    snap = board.snapshot(markets)                   # 盲算之後才抓價
    board.write_board(snap)
    ev = evidence.collect()
    evidence.write(ev)
    print(f"[board] {snap['counts']}  [evidence] 抓取 {ev['fetched_at']['taipei']}")

    rows, fairs = {}, {}
    for m in markets:
        try:
            fairs[m["slug"]], rows[m["slug"]] = gate.read_board(m["slug"])
        except (gate.BlindOrderError, KeyError) as e:
            print(f"  ! {m['slug']}: {e}")
    ev = gate.read_evidence(markets[0]["slug"]) if markets else ev

    checked = sim.check_all(rows)
    print(f"[sim] 檢查先前 tickets {len(checked)} 張")

    exposure, day_pnl = exposure_and_pnl(rows)
    halted = risk_gate.check_daily_loss(day_pnl, day)
    print(f"[risk] 當日損益 {day_pnl:.2f} USD  停機={halted}")

    mirrors = st.mirror_pairs(list(rows.values()))
    now = now_utc()
    new_rows, tally = [], collections.Counter()
    reasons = collections.Counter()
    for slug, row in rows.items():
        fair = fairs[slug]
        for s in strategies_for(row, fair):
            if journal.has(day, s, slug):
                tally["already_logged"] += 1
                continue
            d = DECIDERS[s](fair, row, ev, now)
            size, limit, tid, status, fee = 0.0, "", "", "", ""
            if d["decision"] == "TRADE":
                q_side = fair["fair_yes"] if d["side"] == "YES" else 1 - fair["fair_yes"]
                limit = st.limit_for(d["side"], row, q_side, d["threshold"])
                usd, why = (0.0, "no valid maker price") if limit is None else \
                    risk_gate.size_order(q_side, limit, row, exposure, day=day)
                shares = usd / limit if limit else 0
                min_sz = row.get("min_order_size")
                if usd > 0 and min_sz not in (None, UNAVAILABLE) and shares < float(min_sz):
                    usd, why = 0.0, f"below min order size {min_sz}"
                if usd <= 0:
                    d = dict(d, decision="SKIP", reason=f"risk: {why}")
                else:
                    tid = f"{day}_{s}_{slug}"
                    t, _ = sim.place(tid, s, row, d["side"], limit, shares, usd, row["yes_book"])
                    exposure["by_market"][slug] += usd
                    exposure["by_asset_barrier"][row["asset"]] += usd
                    size, status, fee = usd, t["status"], 0.0
            mir = mirrors.get(slug)
            new_rows.append({
                "time_taipei": stamp(now)["taipei"], "time_utc": stamp(now)["utc"],
                "date_taipei": day, "strategy": s, "market_slug": slug,
                "asset": row["asset"], "kind": row["kind"], "side": d.get("side", ""),
                "fair": fair["fair_yes"], "entry_mid": row["yes_book"]["mid"],
                "edge": d.get("edge", ""), "threshold": d.get("threshold", ""),
                "decision": d["decision"], "reason": d["reason"], "size": size,
                "limit_price": limit or "", "fee": fee, "fill_status": status,
                "filled_shares": "", "ticket_id": tid, "result": "",
                "brier_desk": "", "brier_market": "", "pnl": "",
                "settled_date_taipei": "",
                "mirror": "" if not mir else f"{mir['hit_slug']} ratio={mir['ratio']}{' FLAG' if mir['flag'] else ''}",
            })
            tally[(s, d["decision"])] += 1
            if d["decision"] == "SKIP":
                reasons[(s, d["reason"].split(" (")[0])] += 1
    added = journal.add(new_rows)

    # 回寫成交狀態
    all_rows = journal.load()
    tickets = {t["id"]: t for t in checked}
    for r in all_rows:
        t = tickets.get(r["ticket_id"])
        if t:
            r["fill_status"], r["filled_shares"], r["fee"] = t["status"], t["filled_shares"], t["fee_paid"]
    journal.save(all_rows)

    print(f"[journal] 新增 {added} 列（journal/journal.csv 共 {len(all_rows)} 列）")
    for k in sorted(k for k in tally if k != "already_logged"):
        print(f"  {k[0]} {k[1]}: {tally[k]}")
    if tally["already_logged"]:
        print(f"  今日已記錄而略過: {tally['already_logged']}")
    for (s, why), n in reasons.most_common():
        print(f"  SKIP {s} ×{n}: {why}")
    flags = [k for k, v in mirrors.items() if v["flag"]]
    print(f"[mirror] 配對 {len(mirrors)} 組，比值超出 1.6–2.4 的 {len(flags)} 組")
    print(f"== 完成 {stamp()['taipei']}")


if __name__ == "__main__":
    sys.exit(main())

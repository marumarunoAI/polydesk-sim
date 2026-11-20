"""run_day.py — 一個指令跑完一天（交易員每天台北 13:30 手動執行；本程式不建定時任務）。

順序：結算回填 → 掃描 → blind/ → 盲算 fair/ → 才抓 board/、evidence/（經 gate 讀）
      → 決策 → 風控 → 掛模擬 maker 單 → 檢查先前 tickets 成交 → 寫 journal。
冪等：同一台北日重跑，fair 不重算、journal 同鍵不重記、ticket 同 id 不重建。"""
import collections
import os
import sys

from common import DIRS, ROOT, UNAVAILABLE, now_utc, read_json, stamp, today_tpe
import blind
import board
import evidence
import exits
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
    """由 tickets 算目前曝險（持有 + 掛單中）與當日損益（今日已實現 + 未實現按 mid）。
    出場單不算曝險；已賣出的部分不再算持有，其出場收入計入已實現。"""
    import glob
    exp = {"by_market": collections.Counter(), "by_asset_barrier": collections.Counter()}
    day = today_tpe()
    pnl = 0.0
    exits = {}
    for p in glob.glob(os.path.join(DIRS["tickets"], "*.json")):
        t = read_json(p)
        if t.get("is_exit"):
            exits[t["exit_of"]] = t
    for p in glob.glob(os.path.join(DIRS["tickets"], "*.json")):
        t = read_json(p)
        if t.get("is_exit"):
            continue
        if t["status"] == "settled":
            if t.get("settled_date_taipei") == day:
                pnl += t.get("pnl", 0.0)
            continue
        x = exits.get(t["id"])
        sold = x["filled_shares"] if x else 0.0
        avg = t["fill_cost"] / t["filled_shares"] if t["filled_shares"] else 0.0
        held = t["filled_shares"] - sold
        pending = (t["shares"] - t["filled_shares"]) * t["limit_price"] if t["status"] in ("open", "partial") else 0.0
        live = held * avg + pending
        exp["by_market"][t["slug"]] += live
        exp["by_asset_barrier"][t["asset"]] += live
        if x:
            for f in x["fills"]:
                if f["at"]["taipei"][:10] == day:
                    pnl += f["shares"] * ((1 - f["price"]) - avg)
        mid = (rows_by_slug.get(t["slug"]) or {}).get("yes_book", {}).get("mid", UNAVAILABLE)
        if held > 0 and mid != UNAVAILABLE:
            m = mid if t["outcome"] == "YES" else 1 - mid
            pnl += held * m - held * avg
    return exp, pnl


def stage(name, fn, default):
    """單一階段失敗不中斷整天：印出原因後用預設值繼續。"""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        print(f"[{name}] 失敗但繼續：{type(e).__name__}: {str(e)[:200]}")
        return default


def set_outdir(outdir):
    """把 blind/fair/board/evidence/tickets/journal 全部改放到 outdir 底下。"""
    for k in DIRS:
        DIRS[k] = os.path.join(outdir, k)
        os.makedirs(DIRS[k], exist_ok=True)


STATE_DIRS = ("journal", "fair", "tickets")   # 正式紀錄；tickets/test/ 由 .gitignore 排除


def commit_state(day, repo=None, push=True):
    """把正式紀錄（journal/fair/tickets）commit 並 push 到 main。
    訊息固定 'run_day YYYY-MM-DD'；沒有變化就不產生空 commit；push 失敗只記一行警告，不中斷。
    回傳 'committed' | 'nochange' | 'error'。"""
    import subprocess
    repo = repo or ROOT

    def git(*args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=120)
    try:
        if git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
            print("[git] 警告：不是 git 工作目錄，略過 commit")
            return "error"
        r = git("add", "--", *STATE_DIRS)
        if r.returncode != 0:
            print(f"[git] 警告：git add 失敗：{r.stderr.strip()[-150:]}")
            return "error"
        changed = git("diff", "--cached", "--name-only", "-z", "--", *STATE_DIRS).stdout.split("\0")
        changed = [p for p in changed if p]
        if not changed:
            print("[git] 正式紀錄沒有變化，不 commit")
            return "nochange"
        msg = f"run_day {day}"
        r = git("commit", "-m", msg, "--", *changed)   # 只提交這三個資料夾裡有變動的檔，不夾帶別的暫存內容
        if r.returncode != 0:
            print(f"[git] 警告：commit 失敗：{(r.stderr or r.stdout).strip()[-150:]}")
            return "error"
        h = git("rev-parse", "--short", "HEAD").stdout.strip()
        print(f"[git] commit {h}: {msg}")
        if push:
            p = git("pull", "--rebase", "--autostash")
            if p.returncode != 0:
                git("rebase", "--abort")
                print(f"[git] 警告：pull --rebase 失敗，已保留本機 commit，未 push：{p.stderr.strip()[-150:]}")
                return "committed"
            p = git("push")
            if p.returncode != 0:
                print(f"[git] 警告：push 失敗（本機 commit 已保留）：{p.stderr.strip()[-150:]}")
            else:
                print("[git] push 完成")
        return "committed"
    except Exception as e:  # noqa: BLE001  任何 git 問題都不得中斷 run_day
        print(f"[git] 警告：{type(e).__name__}: {str(e)[:150]}")
        return "error"


def main(argv=None):
    import argparse
    import shutil
    import tempfile
    ap = argparse.ArgumentParser(description="跑完一天的模擬交易台（只模擬，不下真單）")
    ap.add_argument("--outdir", help="所有輸出（blind/fair/board/evidence/tickets/journal）改放這個資料夾")
    ap.add_argument("--dry-run", action="store_true",
                    help="完整跑一遍但不改動真實的 fair/tickets/journal：先把現有狀態複製到暫存資料夾，結束即刪")
    ap.add_argument("--hl-liq-ref", type=int, default=0, metavar="N",
                    help="另外抓 Hyperliquid 前 N 大帳戶的清算價分佈（約 N×0.5 秒，限流＋退避），"
                         "只寫入 evidence['reference']，不進 liquidation_clusters、不影響任何決策；預設 0＝不抓")
    a = ap.parse_args(argv)
    saved = dict(DIRS)
    tmp = None
    if a.dry_run:
        tmp = tempfile.mkdtemp(prefix="polydesk_dry_")
        for k in ("fair", "tickets", "journal"):   # 沿用現有狀態，讓冪等與曝險計算與真跑一致
            src = a.outdir and os.path.join(a.outdir, k) or DIRS[k]
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(tmp, k))
        set_outdir(tmp)
        print(f"[dry-run] 輸出改寫到暫存資料夾 {tmp}（結束後刪除，不影響真實資料）")
    elif a.outdir:
        set_outdir(os.path.abspath(a.outdir))
    try:
        day0 = today_tpe(now_utc())
        out = _run(a.hl_liq_ref)
        if not a.dry_run and not a.outdir:   # dry-run 與 --outdir 都不得 commit 到 repo
            commit_state(day0)
        return out
    finally:
        DIRS.update(saved)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
            print("[dry-run] 暫存資料夾已刪除")


def _run(hl_liq_ref=0):
    t0 = now_utc()
    day = today_tpe(t0)
    print(f"== run_day {day}（台北）開始 {stamp(t0)['taipei']}")

    n_settled = stage("settle", settle.run, 0)
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
    if hl_liq_ref > 0:
        import hl_liq_reference
        ev.setdefault("reference", {})["hl_liquidation_distribution"] = hl_liq_reference.scan(hl_liq_ref)
    evidence.write(ev)
    print(f"[board] {snap['counts']}  [evidence] 抓取 {ev['fetched_at']['taipei']}")

    # 每個市場各自過閘門（board 與 evidence 都要 fair 在先）；任一市場被拒只影響該市場，並記 journal
    rows, fairs, gate_err, ev_checked = {}, {}, {}, None
    for m in markets:
        slug = m["slug"]
        try:
            fairs[slug], rows[slug] = gate.read_board(slug)
            ev_checked = gate.read_evidence(slug)
        except (gate.BlindOrderError, KeyError, OSError, ValueError) as e:
            gate_err[slug] = f"{type(e).__name__}: {e}"
            fairs.pop(slug, None)
            rows.pop(slug, None)
            print(f"  ! {slug}: {gate_err[slug]}")
    print(f"[gate] 通過 {len(rows)} 個，被拒 {len(gate_err)} 個")
    ev = ev_checked  # 只用經過 gate.read_evidence() 的那份；沒有任何市場通過就不會有決策

    checked = stage("sim", lambda: sim.check_all(rows), [])
    print(f"[sim] 檢查先前 tickets {len(checked)} 張")

    ex = stage("exits", lambda: exits.run(rows, fairs, ev, now_utc()), [])
    for pid, why, status in ex:
        print(f"[exit] {pid}: {why} → {status}")
    print(f"[exit] 檢查出場條件，觸發 {len(ex)} 筆")

    exposure, day_pnl = stage("risk", lambda: exposure_and_pnl(rows), ({"by_market": collections.Counter(), "by_asset_barrier": collections.Counter()}, 0.0))
    halted = risk_gate.check_daily_loss(day_pnl, day)
    print(f"[risk] 當日損益 {day_pnl:.2f} USD  停機={halted}")

    mirrors = st.mirror_pairs(list(rows.values()))
    now = now_utc()
    new_rows, tally = [], collections.Counter()
    reasons = collections.Counter()
    by_slug = {m["slug"]: m for m in markets}
    for slug, err in gate_err.items():   # 被閘門拒絕的市場也要記 journal（沒有 fair/價就留空）
        m = by_slug[slug]
        for s in (["S3"] if m["kind"] == "above" else ["S1"]):
            if not journal.has(day, s, slug):
                new_rows.append({
                    "time_taipei": stamp(now)["taipei"], "time_utc": stamp(now)["utc"],
                    "date_taipei": day, "strategy": s, "market_slug": slug, "asset": m["asset"],
                    "kind": m["kind"], "fair": "", "entry_mid": "", "decision": "SKIP",
                    "reason": f"gate rejected: {err}", "size": 0.0, "result": ""})
                tally[(s, "SKIP")] += 1
                reasons[(s, "gate rejected")] += 1
    for slug, row in rows.items():
        fair = fairs[slug]
        for s in strategies_for(row, fair):
            if journal.has(day, s, slug):
                tally["already_logged"] += 1
                continue
            try:
                d = DECIDERS[s](fair, row, ev, now)
            except Exception as e:  # noqa: BLE001  單一市場出錯不中斷整天
                d = {"decision": "SKIP", "reason": f"error: {type(e).__name__}: {str(e)[:120]}"}
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
                    if t["status"] == "rejected_post_only":
                        why = t.get("reject_reason") or "rejected_post_only"
                        bb, ba = t.get("reject_best_bid"), t.get("reject_best_ask")
                        d = dict(d, reason=f"{d['reason']}; {why} (best bid {bb}, best ask {ba})")
                        size, status, fee = 0.0, t["status"], 0.0
                    else:
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
    sys.exit(main(sys.argv[1:]))

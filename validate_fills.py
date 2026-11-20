"""validate_fills.py — 真實資料成交模擬驗證（一次性驗證程序，不是定時任務）。

在活躍市場掛幾筆「測試用」maker 限價買單（is_test=true，放 tickets/test/，不進 journal、績效、風控），
連續跟 N 小時的真實 trades 與訂單簿，檢查 sim.apply_fills() 的成交判斷是否合理，最後寫報告
docs/fill_validation.md。純模擬：沒有任何簽名或送單，只讀公開 API。

用法：python validate_fills.py --hours 3 [--poll 60]   （建議 nohup 背景執行）"""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter

import board
import sim
from common import DIRS, ROOT, UNAVAILABLE, iso_tpe, now_utc, read_json, stamp, write_json

VDIR = os.path.join(ROOT, "validation")
STATE = os.path.join(VDIR, "state.json")
N_MARKETS = 4
SHARES = 10.0


def log(msg):
    line = f"{stamp()['taipei']} {msg}"
    print(line, flush=True)
    with open(os.path.join(VDIR, "run.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def select_markets(window_h=3):
    markets, _ = board.scan_markets()
    snap = board.snapshot(markets)
    cands = []
    for m in snap["markets"]:
        b = m["yes_book"]
        tick = float(m["tick_size"]) if m["tick_size"] != UNAVAILABLE else 0.01
        if UNAVAILABLE in (b["best_bid"], b["best_ask"], b["mid"]):
            continue
        if not (0.08 <= b["mid"] <= 0.92) or b["best_ask"] - b["best_bid"] < 3 * tick - 1e-9:
            continue
        cands.append((m, tick))
    scored = []
    since = time.time() - window_h * 3600
    for m, tick in cands:
        try:
            trades = sim.fetch_trades(m["condition_id"], since, max_pages=2)
        except Exception:
            continue
        scored.append((len(trades), m, tick))
    scored.sort(key=lambda x: -x[0])
    picked, per_asset = [], Counter()
    for n, m, tick in scored:
        if n == 0 or per_asset[m["asset"]] >= 2:
            continue
        picked.append((n, m, tick))
        per_asset[m["asset"]] += 1
        if len(picked) == N_MARKETS:
            break
    return picked, len(cands)


def place_tests(picked, end_epoch):
    plans = []
    for n, m, tick in picked:
        b = m["yes_book"]
        bb, ba = b["best_bid"], b["best_ask"]
        r = lambda x: round(round(x / tick) * tick, 6)
        specs = [
            ("at_bid", "YES", r(bb)),
            ("bid_plus1", "YES", r(bb + tick)),
            ("near_ask", "YES", r(ba - tick)),
            ("far_below", "YES", max(tick, r(bb - 5 * tick))),
            ("no_bid_plus1", "NO", r(1 - ba + tick)),
        ]
        for name, outcome, limit in specs:
            tid = f"TEST_{stamp()['utc'].replace(':', '')}_{m['slug'][:40]}_{name}"
            try:
                t, _ = sim.place(tid, "VALIDATION", m, outcome, limit, SHARES, round(SHARES * limit, 2),
                                 b, is_test=True, cancel_at_epoch=end_epoch)
            except ValueError as e:
                log(f"skip {name} {m['slug']}: {e}")
                continue
            t["case"] = name
            write_json(sim.ticket_path(tid, True), t)
            plans.append(tid)
            log(f"PLACED {name:13s} {outcome:3s} @{limit} x{SHARES:g} queue_ahead={t['queue_ahead']:g} "
                f"[{m['slug']}] book bid/ask {bb}/{ba}")
    return plans


def run(hours, poll, publish_it=True):
    os.makedirs(VDIR, exist_ok=True)
    start = now_utc()
    end_epoch = start.timestamp() + hours * 3600
    picked, ncand = select_markets()
    if not picked:
        log("沒有找到近 3 小時有成交的候選市場，中止")
        return 1
    log(f"候選 {ncand} 個，選中 {len(picked)} 個：" +
        "; ".join(f"{m['slug']}({n} trades/3h)" for n, m, _ in picked))
    tids = place_tests(picked, end_epoch)
    mkts = {m["slug"]: m for _, m, _ in picked}
    raw = {m["condition_id"]: {} for m in mkts.values()}   # condition → trade_key → {trade, first_seen, n}
    series = {s: [] for s in mkts}
    state = {"started": stamp(start), "planned_end": stamp(now_utc().fromtimestamp(end_epoch, start.tzinfo)),
             "markets": {s: {"condition_id": m["condition_id"], "question": m["question"]} for s, m in mkts.items()},
             "tickets": tids}
    write_json(STATE, state)
    log(f"驗證開始 {state['started']['taipei']}，預計結束 {state['planned_end']['taipei']}（台北）")
    prev_poll = start.timestamp()
    first = True
    while now_utc().timestamp() < end_epoch:
        t_poll = now_utc()
        books = board.fetch_books([m["yes_token"] for m in mkts.values()])
        for slug, m in mkts.items():
            try:
                since = (start.timestamp() - 5) if first else prev_poll - 900
                trades = sim.fetch_trades(m["condition_id"], since, max_pages=10)
            except Exception as e:
                log(f"trades fetch failed {slug}: {e}")
                continue
            cb = Counter()
            for tr in trades:
                k = sim.trade_key(tr)
                cb[k] += 1
                rec = raw[m["condition_id"]].setdefault(k, {"trade": tr, "first_seen": t_poll.timestamp(), "n": 0})
                rec["n"] = max(rec["n"], cb[k])
            yb = board.summarize_book(books.get(m["yes_token"]))
            series[slug].append({"t": t_poll.timestamp(), "bid": yb["best_bid"], "ask": yb["best_ask"],
                                 "mid": yb["mid"]})
            for tid in tids:
                t = read_json(sim.ticket_path(tid, True))
                if t["slug"] != slug:
                    continue
                before = t["filled_shares"]
                sim.apply_fills(t, trades, yb, now=t_poll)
                write_json(sim.ticket_path(tid, True), t)
                if t["filled_shares"] > before:
                    log(f"SIM FILL {t['case']} {t['outcome']}@{t['limit_price']} +{t['filled_shares']-before:g} "
                        f"({t['status']}) [{slug}] basis={t['fills'][-1]['basis']}")
        first = False
        prev_poll = t_poll.timestamp()
        write_json(os.path.join(VDIR, "raw.json"), {"series": series, "trades": {
            c: list(v.values()) for c, v in raw.items()}})
        time.sleep(max(1, poll - (now_utc() - t_poll).total_seconds()))
    # 收尾：最後一次 apply（觸發撤單），寫報告
    for tid in tids:
        t = read_json(sim.ticket_path(tid, True))
        m = mkts[t["slug"]]
        trades = [r["trade"] for r in raw[m["condition_id"]].values() for _ in range(r["n"])]
        sim.apply_fills(t, trades, {}, now=now_utc())
        write_json(sim.ticket_path(tid, True), t)
    import validation_report
    validation_report.write(state, mkts, tids, raw, series)
    log("報告已寫入 docs/fill_validation.md")
    if publish_it:
        publish()
    return 0


def publish():
    """只提交驗證報告檔（使用者已指示 commit 到 main）。"""
    files = ["docs/fill_validation.md", "docs/fill_validation_raw.json"]
    files = [f for f in files if os.path.exists(os.path.join(ROOT, f))]
    sh = lambda *a: subprocess.run(a, cwd=ROOT, capture_output=True, text=True)
    sh("git", "add", *files)
    r = sh("git", "commit", "-m", "docs: fill_validation report (real-trade replay of simulated maker test orders)",
           "--only", *files)
    log(f"git commit: {r.stdout.strip()[-120:] or r.stderr.strip()[-200:]}")
    p = sh("git", "push")
    if p.returncode != 0:
        sh("git", "pull", "--rebase", "--autostash")
        p = sh("git", "push")
    log(f"git push rc={p.returncode} {p.stderr.strip()[-150:]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=3.0)
    ap.add_argument("--poll", type=float, default=60.0)
    ap.add_argument("--no-publish", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.hours, a.poll, not a.no_publish))

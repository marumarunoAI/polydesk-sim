"""brier.py — 每週彙總：各策略 brier_desk 對 brier_market、虛擬損益。
已結算 < 30 筆標明「樣本不足」。"""
import os
import sys
from collections import defaultdict
from datetime import date

from common import DIRS
import journal

MIN_SAMPLE = 30


def week_of(d):
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def summarize(rows, week=None):
    g = defaultdict(lambda: {"forecasts": 0, "settled": 0, "bd": [], "bm": [], "pnl": 0.0, "trades": 0})
    for r in rows:
        if week and week_of(r["date_taipei"]) != week:
            continue
        s = g[r["strategy"]]
        s["forecasts"] += 1
        s["trades"] += r["decision"] == "TRADE"
        if r["result"] != "" and r["brier_desk"] not in ("", "unavailable") \
                and r["brier_market"] not in ("", "unavailable"):
            s["settled"] += 1
            s["bd"].append(float(r["brier_desk"]))
            s["bm"].append(float(r["brier_market"]))
        if r["pnl"] not in ("", None):
            s["pnl"] += float(r["pnl"])
    out = []
    for k in sorted(g):
        s = g[k]
        bd = sum(s["bd"]) / len(s["bd"]) if s["bd"] else None
        bm = sum(s["bm"]) / len(s["bm"]) if s["bm"] else None
        if s["settled"] < MIN_SAMPLE:
            note = f"樣本不足（已結算 {s['settled']} < {MIN_SAMPLE}）"
        elif bd >= bm:
            note = "desk Brier 不優於市場 → 觸發停用規則（S1/S3）"
        else:
            note = "desk 優於市場"
        out.append({"strategy": k, "forecasts": s["forecasts"], "trades": s["trades"],
                    "settled": s["settled"], "brier_desk": bd, "brier_market": bm,
                    "pnl": round(s["pnl"], 2), "note": note})
    return out


def fmt(rows):
    f = lambda x: "-" if x is None else f"{x:.4f}"
    lines = ["| 策略 | 預測 | 交易 | 已結算 | brier_desk | brier_market | 虛擬損益 USD | 備註 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['strategy']} | {r['forecasts']} | {r['trades']} | {r['settled']} | "
                     f"{f(r['brier_desk'])} | {f(r['brier_market'])} | {r['pnl']:.2f} | {r['note']} |")
    return "\n".join(lines)


def main(argv):
    rows = journal.load()
    week = argv[1] if len(argv) > 1 else None
    text = f"# Brier 彙總 {week or '全部'}\n\n" + fmt(summarize(rows, week)) + "\n"
    name = f"weekly_{week}.md" if week else "brier_all.md"
    with open(os.path.join(DIRS["journal"], name), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv)

"""gate.py — 盲算順序的唯一關卡（DESK_RULES 第 1 條）。

讀 board/ 或 evidence/ 只准經過這裡：
  - fair/<slug>.json 必須存在；
  - fair 的時間戳必須早於讀價時間，也早於該份 board/evidence 的抓取時間。
否則 raise BlindOrderError。"""
import os

from common import DIRS, now_utc, read_json


class BlindOrderError(RuntimeError):
    pass


def fair_path(slug):
    return os.path.join(DIRS["fair"], f"{slug}.json")


def require_fair(slug, read_time=None):
    p = fair_path(slug)
    if not os.path.exists(p):
        raise BlindOrderError(f"拒絕讀價：{slug} 沒有 fair 檔（先盲算）")
    fair = read_json(p)
    t_read = (read_time or now_utc()).timestamp()
    if fair["ts"]["epoch"] >= t_read:
        raise BlindOrderError(f"拒絕讀價：{slug} 的 fair 時間戳不早於讀價時間")
    return fair


def _check_after(fair, fetched, slug, what):
    if fetched["epoch"] <= fair["ts"]["epoch"]:
        raise BlindOrderError(
            f"拒絕讀價：{what} 抓取時間 {fetched['utc']} 不晚於 {slug} 的 fair "
            f"{fair['ts']['utc']}（價格必須在盲算之後才抓）")


def read_board(slug, board_path=None):
    """回傳 (fair, board 中該市場那一列)。"""
    fair = require_fair(slug)
    board = read_json(board_path or os.path.join(DIRS["board"], "latest.json"))
    _check_after(fair, board["fetched_at"], slug, "board")
    for row in board["markets"]:
        if row["slug"] == slug:
            return fair, row
    raise KeyError(f"{slug} 不在 board 裡")


def read_evidence(slug, evidence_path=None):
    fair = require_fair(slug)
    ev = read_json(evidence_path or os.path.join(DIRS["evidence"], "latest.json"))
    _check_after(fair, ev["fetched_at"], slug, "evidence")
    return ev

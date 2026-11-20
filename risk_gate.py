"""risk_gate.py — 虛擬資金風控（DESK_RULES 第 4、5、7、9、11 條）。
常數可調；策略規則本身以 DESK_RULES.md 為準。"""
import os

from common import DIRS, today_tpe

BANKROLL = 1000.0               # 虛擬資金 USD
KELLY_MULT = 0.10               # Kelly × 0.1–0.25（負責人可在此範圍內調）
KELLY_MIN, KELLY_MAX = 0.10, 0.25
MAX_PER_BARRIER = 0.03          # 單一觸價市場 ≤ 3%
MAX_ASSET_BARRIERS = 0.06       # 同一資產所有 barrier 合計 ≤ 6%（BTC、ETH 各自計）
CERTAIN_MIN, CERTAIN_MAX = 0.02, 0.05  # 確定性部位 2–5%（S5，第一版未啟用）
MAX_BUY_PRICE = 0.97            # 尚未發生的事，絕不在 0.97 以上買
DAILY_LOSS_LIMIT = 0.02         # 每日虧損 2% → 當日唯讀
EDGE_BUFFER = 0.02              # 進場門檻 fee + 2 pp
SHORT_RECURRENCE = {"5m", "15m", "hourly", "4h"}
SHORT_TAGS = {"5m", "15m", "1h", "4h", "hourly"}
BANNED_TAGS = {"sports", "politics", "elections", "election", "us-election",
               "geopolitics", "world-elections", "global-elections"}

assert KELLY_MIN <= KELLY_MULT <= KELLY_MAX


def excluded(tags, recurrences=()):
    """短於日線、體育、選舉、政治 → 回傳原因；可交易回傳 None。"""
    tags = {(t or "").lower() for t in tags}
    rec = {(r or "").lower() for r in recurrences}
    if rec & SHORT_RECURRENCE or tags & SHORT_TAGS:
        return "shorter than daily"
    if tags & BANNED_TAGS:
        return "sports/election/politics"
    return None


def kelly_fraction(q, price):
    """買一份 price、贏機率 q 的二元合約，完整 Kelly 比例。"""
    if price <= 0 or price >= 1 or q <= price:
        return 0.0
    return (q - price) / (1 - price)


def halt_path(day=None):
    return os.path.join(DIRS["journal"], f"halt_{day or today_tpe()}")


def halted(day=None):
    return os.path.exists(halt_path(day))


def check_daily_loss(day_pnl, day=None):
    """當日損益 ≤ −2% 資金 → 寫 halt 檔，當日停到隔天。回傳是否停機。"""
    if day_pnl <= -DAILY_LOSS_LIMIT * BANKROLL:
        with open(halt_path(day), "w") as f:
            f.write(f"day_pnl={day_pnl:.2f}\n")
    return halted(day)


def size_order(q, price, market, exposure, kind="barrier", day=None):
    """回傳 (usd, reason)。usd=0 代表擋下。
    exposure: {"by_market": {slug: usd}, "by_asset_barrier": {asset: usd}}"""
    why = excluded(market.get("tags") or [])
    if why:
        return 0.0, f"excluded market: {why}"
    if halted(day):
        return 0.0, "daily loss limit hit: read-only until tomorrow"
    if price >= MAX_BUY_PRICE:
        return 0.0, f"price {price} >= {MAX_BUY_PRICE}"
    f = kelly_fraction(q, price) * KELLY_MULT
    if f <= 0:
        return 0.0, "no Kelly edge"
    usd = f * BANKROLL
    if kind == "certain":
        usd = min(max(usd, CERTAIN_MIN * BANKROLL), CERTAIN_MAX * BANKROLL)
        return round(usd, 2), "ok"
    used_m = exposure.get("by_market", {}).get(market["slug"], 0.0)
    used_a = exposure.get("by_asset_barrier", {}).get(market["asset"], 0.0)
    usd = min(usd, MAX_PER_BARRIER * BANKROLL - used_m,
              MAX_ASSET_BARRIERS * BANKROLL - used_a)
    if usd <= 0:
        return 0.0, "exposure cap reached"
    return round(usd, 2), "ok"

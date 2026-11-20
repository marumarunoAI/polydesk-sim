"""手續費（依官方文件，2026-11-20 17:5x 台北親自讀取核實）：

  fee = shares × feeRate × price × (1 − price)；maker 不收平台費。

費率表依「下單／事件時間」切換：
  - 切換前（現行）：https://docs.polymarket.com/trading/fees
      Crypto taker 係數 0.07、maker 0、maker 返佣 = 每日市場返佣池（20%，按比例分配，個別帳號無法預估）
  - 切換後（2026-11-20 23:59 UTC = 台北 2026-11-21 07:59 起）：
      https://docs.polymarket.com/programs/fee-and-rebate-changes-november-2026
      Crypto — BTC 5/15 分鐘 up/down：0.05；Crypto — 其他所有市場（含本台的日線觸價與 above）：0.01
      maker 仍 0；maker 返佣改成 30 天 maker 加權量分級（<$20 萬 0%、$20 萬起 3%、$100 萬起 7%、
      $400 萬起 10%、$1,000 萬起 15%，返佣 = 該檔位% × 自己成交產生的 taker 費）
本台虛擬帳號的 30 天量遠低於 $20 萬 → 切換後 maker 返佣 0%；切換前的每日返佣池無法估算，也記 0（保守）。
模擬成交的 maker 實收費率 = 0；taker 公式只用在進場門檻 fee + 2pp。
"""
from datetime import datetime, timezone

CHANGE_AT = datetime(2026, 11, 20, 23, 59, tzinfo=timezone.utc)
SOURCE_BEFORE = "https://docs.polymarket.com/trading/fees"
SOURCE_AFTER = "https://docs.polymarket.com/programs/fee-and-rebate-changes-november-2026"
CHECKED_AT = "2026-11-20 17:5x 台北 (UTC+8)"

# 類別 → taker 係數
TAKER_BEFORE = {"crypto": 0.07, "crypto_btc_5m_15m": 0.07}
TAKER_AFTER = {"crypto": 0.01, "crypto_btc_5m_15m": 0.05}
MAKER_FEE_RATE = 0.0
# 切換後的 maker 返佣分級：(30 天 maker 加權量下限 USD, 返佣比例)
MAKER_REBATE_TIERS_AFTER = [(0, 0.0), (200_000, 0.03), (1_000_000, 0.07), (4_000_000, 0.10), (10_000_000, 0.15)]


def _when(when):
    if when is None:
        from common import now_utc
        when = now_utc()
    return when


def taker_fee_rate(when=None, category="crypto"):
    """依時間選 taker 係數。when 為 timezone-aware datetime；邊界 23:59:00Z 起用新費率。"""
    table = TAKER_AFTER if _when(when) >= CHANGE_AT else TAKER_BEFORE
    return table[category]


def taker_fee_per_share(p, when=None, category="crypto", rate=None):
    r = taker_fee_rate(when, category) if rate is None else rate
    return r * p * (1 - p)


def fee_source(when=None):
    return SOURCE_AFTER if _when(when) >= CHANGE_AT else SOURCE_BEFORE


def maker_fee(shares, p, rate=MAKER_FEE_RATE):
    return round(shares * rate * p * (1 - p), 5)


def maker_rebate_rate(maker_weighted_volume_30d=0.0, when=None):
    """本台虛擬帳號的 maker 返佣比例。切換前為每日池（無法預估）→ 0。"""
    if _when(when) < CHANGE_AT:
        return 0.0
    rate = 0.0
    for floor, r in MAKER_REBATE_TIERS_AFTER:
        if maker_weighted_volume_30d >= floor:
            rate = r
    return rate

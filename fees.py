"""手續費（依 Polymarket 官方文件 https://docs.polymarket.com/trading/fees，2026-11-20 讀取）：
fee = C × feeRate × p × (1 − p)；Crypto 類 taker feeRate = 0.07、maker = 0（maker 從不收費）。
文件註明 2026-11-20 23:59 UTC 起 taker 費與返佣會調整，屆時需重新核實。"""
TAKER_FEE_RATE = 0.07
MAKER_FEE_RATE = 0.0
SOURCE = "https://docs.polymarket.com/trading/fees"


def taker_fee_per_share(p, rate=TAKER_FEE_RATE):
    return rate * p * (1 - p)


def maker_fee(shares, p, rate=MAKER_FEE_RATE):
    return round(shares * rate * p * (1 - p), 5)

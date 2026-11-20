import unittest
from datetime import datetime, timedelta, timezone

from helpers import TempDirs  # noqa: F401
import fees
import strategies as st

U = timezone.utc
CUT = datetime(2026, 11, 20, 23, 59, tzinfo=U)
ROW = {"slug": "s", "asset": "BTC", "kind": "above", "end_utc": "2099-01-01T00:00:00Z",
       "yes_book": {"best_bid": 0.49, "best_ask": 0.51, "mid": 0.5}}
FAIR = {"fair_yes": 0.5 + 0.03, "inputs_unavailable": []}  # 邊際 3pp


class FeeSwitchTest(unittest.TestCase):
    def test_rate_switches_at_2359_utc(self):
        self.assertEqual(fees.taker_fee_rate(CUT - timedelta(seconds=1)), 0.07)
        self.assertEqual(fees.taker_fee_rate(CUT), 0.01)
        self.assertEqual(fees.taker_fee_rate(CUT + timedelta(hours=8)), 0.01)

    def test_taipei_0759_is_the_same_instant(self):
        tpe = timezone(timedelta(hours=8))
        self.assertEqual(fees.taker_fee_rate(datetime(2026, 11, 21, 7, 58, 59, tzinfo=tpe)), 0.07)
        self.assertEqual(fees.taker_fee_rate(datetime(2026, 11, 21, 7, 59, 0, tzinfo=tpe)), 0.01)

    def test_formula_unchanged_values(self):
        b, a = CUT - timedelta(minutes=1), CUT
        self.assertAlmostEqual(fees.taker_fee_per_share(0.5, when=b) * 100, 1.75)
        self.assertAlmostEqual(fees.taker_fee_per_share(0.5, when=a) * 100, 0.25)
        self.assertAlmostEqual(fees.taker_fee_per_share(0.2, when=a), 0.01 * 0.2 * 0.8)

    def test_btc_5m_15m_category_after(self):
        self.assertEqual(fees.taker_fee_rate(CUT, "crypto_btc_5m_15m"), 0.05)

    def test_maker_never_pays(self):
        self.assertEqual(fees.maker_fee(100, 0.5), 0)

    def test_rebate_zero_for_small_account(self):
        self.assertEqual(fees.maker_rebate_rate(1000, CUT - timedelta(days=1)), 0)
        self.assertEqual(fees.maker_rebate_rate(1000, CUT), 0)
        self.assertEqual(fees.maker_rebate_rate(250_000, CUT), 0.03)
        self.assertEqual(fees.maker_rebate_rate(10_000_000, CUT), 0.15)

    def test_entry_threshold_crosses_switch(self):
        # 邊際 3pp：舊費率門檻 0.0175+0.02=0.0375 → 無優勢；新費率 0.0025+0.02=0.0225 → 有優勢
        ev = None
        d_before = st._base(FAIR, ROW, CUT - timedelta(seconds=1))[0]
        d_after = st._base(FAIR, ROW, CUT)[0]
        self.assertAlmostEqual(d_before[3], 0.0375)
        self.assertAlmostEqual(d_after[3], 0.0225)
        self.assertLess(abs(FAIR["fair_yes"] - 0.5), d_before[3])
        self.assertGreater(abs(FAIR["fair_yes"] - 0.5), d_after[3])
        self.assertEqual(st.decide_s3(FAIR, ROW, _EV, CUT - timedelta(seconds=1))["decision"], "NO_EDGE")
        self.assertEqual(st.decide_s3(FAIR, ROW, _EV, CUT)["decision"], "TRADE")


def _v(x):
    return {"value": x}


_EV = {"assets": {"BTC": {"binance_funding": _v("unavailable"), "okx_funding": _v(0.0001),
                          "deribit_funding": _v("unavailable"), "hyperliquid_funding": _v("unavailable"),
                          "binance_oi": _v("unavailable"), "okx_oi": _v(1.0), "hyperliquid_oi": _v("unavailable"),
                          "deribit_oi": _v("unavailable"), "etf_flow_prev_day": _v(100.0)}},
       "global": {"macro_events_next8d": _v([])}}

if __name__ == "__main__":
    unittest.main()

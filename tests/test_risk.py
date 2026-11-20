import unittest

from helpers import TempDirs
import fees
import risk_gate as rg

M = {"slug": "m1", "asset": "BTC"}


class RiskTest(unittest.TestCase):
    def test_never_buy_at_097(self):
        with TempDirs():
            self.assertEqual(rg.size_order(0.999, 0.97, M, {})[0], 0)

    def test_per_barrier_cap(self):
        with TempDirs():
            usd, _ = rg.size_order(0.9, 0.1, M, {})
            self.assertLessEqual(usd, 30.0)
            usd, why = rg.size_order(0.9, 0.1, M, {"by_market": {"m1": 30.0}})
            self.assertEqual(usd, 0)

    def test_asset_barrier_cap(self):
        with TempDirs():
            usd, _ = rg.size_order(0.9, 0.1, M, {"by_asset_barrier": {"BTC": 55.0}})
            self.assertLessEqual(usd, 5.0)
            usd, _ = rg.size_order(0.9, 0.1, {"slug": "e", "asset": "ETH"},
                                   {"by_asset_barrier": {"BTC": 60.0}})
            self.assertGreater(usd, 0)  # ETH 另計

    def test_kelly(self):
        self.assertAlmostEqual(rg.kelly_fraction(0.6, 0.5), 0.2)
        self.assertEqual(rg.kelly_fraction(0.4, 0.5), 0)

    def test_daily_loss_halt(self):
        with TempDirs():
            self.assertFalse(rg.check_daily_loss(-19.0))
            self.assertTrue(rg.check_daily_loss(-20.0))
            self.assertEqual(rg.size_order(0.9, 0.1, M, {})[0], 0)

    def test_excluded(self):
        self.assertTrue(rg.excluded(["crypto", "1H"]))
        self.assertTrue(rg.excluded(["crypto"], ["15m"]))
        self.assertTrue(rg.excluded(["politics", "bitcoin"]))
        self.assertIsNone(rg.excluded(["crypto", "bitcoin"], ["daily"]))
        with TempDirs():
            self.assertEqual(rg.size_order(0.9, 0.1, {"slug": "x", "asset": "BTC", "tags": ["sports"]}, {})[0], 0)

    def test_fees(self):
        self.assertAlmostEqual(fees.taker_fee_per_share(0.5) * 100, 1.75)
        self.assertEqual(fees.maker_fee(100, 0.5), 0)


if __name__ == "__main__":
    unittest.main()

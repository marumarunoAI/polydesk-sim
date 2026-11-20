import unittest
from unittest import mock

from helpers import TempDirs
import common
import journal
import risk_gate
import settle
import sim
import strategies as st

ROW = {"slug": "btc-above-60k", "asset": "BTC", "kind": "above", "level": 60000,
       "condition_id": "0xc", "yes_token": "Y", "no_token": "N", "tick_size": 0.01,
       "end_utc": "2099-01-01T00:00:00Z", "min_order_size": 5, "tags": ["crypto"],
       "question": "Will the price of Bitcoin be above $60,000 on November 20?",
       "yes_book": {"best_bid": 0.40, "best_ask": 0.44, "mid": 0.42,
                    "bids_top5": [{"price": 0.40, "size": 10}],
                    "asks_top5": [{"price": 0.44, "size": 10}]}}
FAIR = {"fair_yes": 0.60, "inputs_unavailable": [], "fomc_in_window": False}


def ev(avail=True):
    v = lambda x: {"value": x if avail else "unavailable"}
    return {"assets": {"BTC": {"binance_funding": v(0.0001), "hyperliquid_funding": {"value": 0.00001, "per_8h": 0.00008},
                               "binance_oi": v(1.0), "hyperliquid_oi": v(1.0),
                               "etf_flow_prev_day": v(100.0),
                               "liquidation_clusters": {"value": "unavailable", "reason": "no free source"}}},
            "global": {"macro_releases_today": v("none")}}


class PipelineTest(unittest.TestCase):
    def test_s3_skip_when_tape_unavailable(self):
        d = st.decide_s3(FAIR, ROW, ev(False))
        self.assertEqual(d["decision"], "SKIP")
        self.assertIn("unavailable", d["reason"])

    def test_s3_trade_places_maker_ticket(self):
        with TempDirs():
            d = st.decide_s3(FAIR, ROW, ev(True))
            self.assertEqual((d["decision"], d["side"]), ("TRADE", "YES"))
            limit = st.limit_for("YES", ROW, 0.60, d["threshold"])
            self.assertEqual(limit, 0.41)  # best bid + 1 tick, below best ask
            usd, why = risk_gate.size_order(0.60, limit, ROW, {})
            self.assertTrue(0 < usd <= 30, (usd, why))
            t, created = sim.place("x", "S3", ROW, "YES", limit, usd / limit, usd, ROW["yes_book"])
            self.assertTrue(created)
            self.assertEqual(t["status"], "open")

    def test_s1_always_skips_without_liquidation_map(self):
        row = dict(ROW, kind="reach", direction="up")
        d = st.decide_s1(FAIR, row, ev(True))
        self.assertEqual(d["decision"], "SKIP")
        self.assertIn("liquidation_clusters", d["reason"])

    def test_s2_longshot_signal(self):
        row = dict(ROW, kind="reach", yes_book=dict(ROW["yes_book"], mid=0.10, best_bid=0.09, best_ask=0.11))
        d = st.decide_s2({"fair_yes": 0.02, "inputs_unavailable": [], "fomc_in_window": True}, row, ev(True))
        self.assertEqual(d["reason"], "veto: FOMC meeting inside window")

    def test_journal_idempotent_and_settle(self):
        with TempDirs():
            r = {"date_taipei": "2026-11-20", "strategy": "S3", "market_slug": "m",
                 "fair": 0.8, "entry_mid": 0.6, "result": "", "ticket_id": "", "pnl": ""}
            self.assertEqual(journal.add([r]), 1)
            self.assertEqual(journal.add([r]), 0)
            with mock.patch.object(settle, "resolution", return_value=1):
                self.assertEqual(settle.run(), 1)
            row = journal.load()[0]
            self.assertAlmostEqual(float(row["brier_desk"]), 0.04)
            self.assertAlmostEqual(float(row["brier_market"]), 0.16)


if __name__ == "__main__":
    unittest.main()

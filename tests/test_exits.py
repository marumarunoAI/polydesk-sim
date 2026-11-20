import csv
import os
import unittest
from datetime import timedelta

from helpers import TempDirs
import common
import exits
import journal
import settle
import sim

MKT = {"slug": "m", "asset": "BTC", "kind": "reach", "condition_id": "0xc", "level": 70000,
       "yes_token": "Y", "no_token": "N", "tick_size": 0.01,
       "end_utc": "2099-01-01T00:00:00Z"}


def row(bid, ask, **kw):
    r = dict(MKT, tags=[], yes_book={
        "best_bid": bid, "best_ask": ask, "mid": round((bid + ask) / 2, 6),
        "bids_top5": [{"price": bid, "size": 50}], "asks_top5": [{"price": ask, "size": 40}]})
    r.update(kw)
    return r


def filled_parent(strategy="S1", outcome="YES", limit=0.30, shares=10, end="2099-01-01T00:00:00Z"):
    m = dict(MKT, end_utc=end)
    t, _ = sim.place("p1", strategy, m, outcome, limit, shares, shares * limit, row(0.29, 0.35)["yes_book"])
    t["filled_shares"] = shares
    t["fill_cost"] = shares * limit
    t["status"] = "filled"
    common.write_json(sim.ticket_path("p1"), t)
    return t


class ExitTest(unittest.TestCase):
    def setUp(self):
        self.td = TempDirs().__enter__()

    def tearDown(self):
        self.td.__exit__()

    def test_margin_below_half_pp_triggers(self):
        t = filled_parent()
        r = exits.exit_reason(t, {"fair_yes": 0.335}, row(0.33, 0.34), None)  # 邊際 0.5pp 剛好不觸發？ mid .335 → 0
        self.assertIn("< 0.5pp", r)
        self.assertIsNone(exits.exit_reason(t, {"fair_yes": 0.45}, row(0.33, 0.34), None))

    def test_no_side_margin_sign(self):
        t = filled_parent(outcome="NO", limit=0.60)
        # 持有 NO：fair_yes 0.30、mid 0.335 → 邊際 3.5pp → 不出場；fair_yes 0.34 → −0.5pp → 出場
        self.assertIsNone(exits.exit_reason(t, {"fair_yes": 0.30}, row(0.33, 0.34), None))
        self.assertIn("< 0.5pp", exits.exit_reason(t, {"fair_yes": 0.34}, row(0.33, 0.34), None))

    def test_24h_rule_s1_not_s3(self):
        end = (common.now_utc() + timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        s1 = filled_parent("S1", end=end)
        self.assertIn("24h", exits.exit_reason(s1, {"fair_yes": 0.9}, row(0.33, 0.34), None))
        s3 = dict(s1, strategy="S3")
        self.assertIsNone(exits.exit_reason(s3, {"fair_yes": 0.9}, row(0.33, 0.34), None))

    def test_s2_veto_appears(self):
        t = filled_parent("S2", outcome="NO", limit=0.6)
        f = {"fair_yes": 0.01, "fomc_in_window": True}
        self.assertIn("FOMC", exits.exit_reason(t, f, row(0.33, 0.34), None))
        ev = {"assets": {"BTC": {"liquidation_clusters": {"value": [{"price": 69000, "usd": 11e9}]},
                                 "binance_funding": {"value": "unavailable"}}}}
        self.assertIn("cluster", exits.exit_reason(t, {"fair_yes": 0.01, "fomc_in_window": False}, row(0.33, 0.34), ev))

    def test_unavailable_inputs_do_not_trigger(self):
        t = filled_parent()
        self.assertIsNone(exits.exit_reason(t, {"fair_yes": "unavailable"}, row(0.33, 0.34), None))

    def test_exit_is_maker_sell_at_ask_minus_tick_never_mid(self):
        t = filled_parent()
        x, created = sim.place_exit(t, row(0.33, 0.37), row(0.33, 0.37)["yes_book"], "test")
        self.assertTrue(created)
        self.assertEqual(x["sell_price"], 0.36)  # ask 0.37 − 1 tick，不是 mid 0.35
        self.assertEqual((x["outcome"], x["limit_price"]), ("NO", 0.64))
        # 價差 1 tick → 掛在最佳賣價排隊
        t2 = dict(t, id="p2")
        x2, _ = sim.place_exit(t2, row(0.33, 0.34), row(0.33, 0.34)["yes_book"], "test")
        self.assertEqual(x2["sell_price"], 0.34)
        self.assertEqual(x2["queue_ahead"], 40)

    def test_exit_fills_only_when_real_buyers_trade_through(self):
        t = filled_parent()
        r = row(0.33, 0.37)
        x, _ = sim.place_exit(t, r, r["yes_book"], "test")
        t0 = x["placed_at"]["epoch"]
        # mid(0.35) 到過也不算；taker 買 YES 在 0.36 → 同價，要先扣排隊（賣單簿 0.36 沒量 → queue 0）
        x = sim.apply_fills(x, [], r["yes_book"])
        self.assertEqual(x["filled_shares"], 0)
        buy = {"outcome": "Yes", "side": "BUY", "price": 0.37, "size": 4, "timestamp": t0 + 3}
        x = sim.apply_fills(x, [buy], r["yes_book"])  # 買在 0.37 > 我們賣價 0.36 → 穿過
        self.assertEqual(x["filled_shares"], 4)
        self.assertAlmostEqual(sim.exit_proceeds(x), 4 * 0.36)

    def test_run_places_once_and_logs(self):
        filled_parent()
        r = row(0.33, 0.35)
        out = exits.run({"m": r}, {"m": {"fair_yes": 0.34}}, None)
        self.assertEqual(len(out), 1)
        self.assertEqual(sim.read_exit("p1")["exit_reason"][:4], "edge")
        self.assertEqual(exits.run({"m": r}, {"m": {"fair_yes": 0.34}}, None), [])  # 冪等
        with open(os.path.join(common.DIRS["journal"], "exits.csv"), encoding="utf-8") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)

    def test_settle_pnl_with_partial_exit(self):
        t = filled_parent(shares=10, limit=0.30)
        r = row(0.33, 0.35)
        x, _ = sim.place_exit(t, r, r["yes_book"], "test")
        x["filled_shares"], x["fill_cost"] = 4, 4 * x["limit_price"]  # 賣出 4 股 @ 0.34
        common.write_json(sim.ticket_path(x["id"]), x)
        journal.save([{"date_taipei": "2020-01-01", "strategy": "S1", "market_slug": "m", "fair": 0.5,
                       "entry_mid": 0.3, "result": "", "ticket_id": "p1", "pnl": ""}])
        from unittest import mock
        with mock.patch.object(settle, "resolution", return_value=1),              mock.patch.object(sim, "fetch_trades", return_value=[]):
            settle.run()
        pnl = float(journal.load()[0]["pnl"])
        # 賣 4 股收入 4×0.34；剩 6 股 YES 贏 → +6；成本 3.0
        self.assertAlmostEqual(pnl, 4 * 0.34 + 6 - 3.0, places=4)


if __name__ == "__main__":
    unittest.main()

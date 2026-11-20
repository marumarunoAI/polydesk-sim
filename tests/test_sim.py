import unittest
from datetime import timedelta

from helpers import TempDirs
import common
import sim

MKT = {"slug": "m", "asset": "BTC", "kind": "reach", "condition_id": "0xc",
       "yes_token": "Y", "no_token": "N", "end_utc": "2099-01-01T00:00:00Z"}
BOOK = {"bids_top5": [{"price": 0.30, "size": 5}, {"price": 0.29, "size": 50}],
        "asks_top5": [{"price": 0.34, "size": 40}, {"price": 0.35, "size": 100}],
        "mid": 0.32}


def tr(outcome, side, price, size, ts):
    return {"outcome": outcome, "side": side, "price": price, "size": size, "timestamp": ts}


class SimTest(unittest.TestCase):
    def setUp(self):
        self.td = TempDirs().__enter__()
        self.t, _ = sim.place("t1", "S1", MKT, "YES", 0.30, 10, 3.0, BOOK)
        self.t0 = self.t["placed_at"]["epoch"]

    def tearDown(self):
        self.td.__exit__()

    def test_place_is_idempotent(self):
        _, created = sim.place("t1", "S1", MKT, "YES", 0.30, 10, 3.0, BOOK)
        self.assertFalse(created)

    def test_maker_only(self):
        with self.assertRaises(ValueError):
            sim.place("t2", "S1", MKT, "YES", 0.34, 10, 3.4, BOOK)

    def test_mid_touch_alone_no_fill(self):
        book = dict(BOOK, mid=0.30)  # mid 碰到限價，但沒人賣到 0.30
        t = sim.apply_fills(self.t, [], book)
        self.assertEqual(t["filled_shares"], 0)
        self.assertEqual(t["status"], "open")

    def test_buy_trades_do_not_fill_our_bid(self):
        t = sim.apply_fills(self.t, [tr("Yes", "BUY", 0.25, 100, self.t0 + 1)], BOOK)
        self.assertEqual(t["filled_shares"], 0)

    def test_trade_through_partial(self):
        t = sim.apply_fills(self.t, [tr("Yes", "SELL", 0.29, 3, self.t0 + 1)], BOOK)
        self.assertEqual(t["filled_shares"], 3)
        self.assertEqual(t["status"], "partial")
        self.assertEqual(t["fee_paid"], 0)

    def test_queue_ahead_at_limit(self):
        # 掛單時 0.30 已有 5 股排在前面；0.30 成交 8 股 → 我們只拿 3 股
        t = sim.apply_fills(self.t, [tr("Yes", "SELL", 0.30, 8, self.t0 + 1)], BOOK)
        self.assertEqual(t["filled_shares"], 3)

    def test_old_trades_ignored(self):
        t = sim.apply_fills(self.t, [tr("Yes", "SELL", 0.10, 100, self.t0 - 10)], BOOK)
        self.assertEqual(t["filled_shares"], 0)

    def test_complement_buy_maps_to_our_bid(self):
        # taker 買 NO @0.75 = 賣 YES @0.25 → 穿過我們 0.30 的 YES 買單
        t = sim.apply_fills(self.t, [tr("No", "BUY", 0.75, 50, self.t0 + 1)], BOOK)
        self.assertEqual(t["status"], "filled")
        self.assertEqual(t["filled_shares"], 10)

    def test_book_crossed_fills_by_depth(self):
        book = {"bids_top5": [{"price": 0.28, "size": 5}],
                "asks_top5": [{"price": 0.30, "size": 4}, {"price": 0.31, "size": 100}]}
        t = sim.apply_fills(self.t, [], book)
        self.assertEqual(t["filled_shares"], 4)

    def test_no_side_ticket(self):
        t, _ = sim.place("t3", "S2", MKT, "NO", 0.60, 10, 6.0, BOOK)  # NO ask = 1-0.30 = 0.70
        t = sim.apply_fills(t, [tr("No", "SELL", 0.60, 4, t["placed_at"]["epoch"] + 1),
                                tr("Yes", "BUY", 0.45, 2, t["placed_at"]["epoch"] + 1)], BOOK)
        # NO 同價排隊量 = YES 賣單在 0.40 的量 = 0 → 0.60 的 4 股 + 換算 0.55 的 2 股 = 6
        self.assertEqual(t["filled_shares"], 6)

    def test_same_trade_not_double_counted_and_late_trade_still_seen(self):
        a = dict(tr("Yes", "SELL", 0.29, 3, self.t0 + 5), transaction_hash="0xa", token_id="Y")
        t = sim.apply_fills(self.t, [a], BOOK)
        t = sim.apply_fills(t, [a], BOOK)  # 同一筆再出現（重疊視窗）→ 不重複計
        self.assertEqual(t["filled_shares"], 3)
        late = dict(tr("Yes", "SELL", 0.28, 2, self.t0 + 2), transaction_hash="0xb", token_id="Y")
        t = sim.apply_fills(t, [a, late], BOOK)  # 時間戳較早但晚到的成交 → 仍計入
        self.assertEqual(t["filled_shares"], 5)

    def test_test_tickets_isolated(self):
        t, _ = sim.place("tt", "S1", MKT, "YES", 0.30, 10, 3.0, BOOK, is_test=True)
        self.assertTrue(t["is_test"])
        self.assertNotIn("tt", [x["id"] for x in sim.open_tickets()])

    def test_cancel_before_expiry(self):
        t = dict(self.t, cancel_at_epoch=self.t0 + 5)
        t = sim.apply_fills(t, [], BOOK, now=common.now_utc() + timedelta(seconds=10))
        self.assertEqual(t["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()

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

    def test_place_crossing_rejected_post_only(self):
        t, created = sim.place("t2", "S1", MKT, "YES", 0.34, 10, 3.4, BOOK)
        self.assertTrue(created)
        self.assertEqual(t["status"], "rejected_post_only")
        self.assertEqual(t["filled_shares"], 0)
        self.assertEqual(t["fee_paid"], 0)
        self.assertEqual(t["fills"], [])
        self.assertIn("rejected_post_only", t["reject_reason"])
        self.assertEqual(t["reject_best_ask"], 0.34)
        self.assertEqual(t["reject_best_bid"], 0.30)
        # 拒單後即使有會穿過的成交紀錄，也不成交、不記手續費
        t = sim.apply_fills(t, [tr("Yes", "SELL", 0.10, 100, t["placed_at"]["epoch"] + 1)], BOOK)
        self.assertEqual(t["filled_shares"], 0)
        self.assertEqual(t["status"], "rejected_post_only")
        self.assertEqual(t["fee_paid"], 0)

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

    def test_book_cross_without_trades_does_not_fill(self):
        # 掛單後對手最佳賣價穿過／碰到我們限價，但沒有真實成交 → 不成交、也不拒單
        self.t["queue_ahead"] = 0
        book = {"bids_top5": [{"price": 0.28, "size": 5}],
                "asks_top5": [{"price": 0.29, "size": 40}],
                "best_bid": 0.28, "best_ask": 0.29}
        t = sim.apply_fills(self.t, [], book)
        self.assertEqual(t["filled_shares"], 0)
        self.assertEqual(t["status"], "open")
        self.assertEqual(t["fee_paid"], 0)

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

    def test_late_trade_still_fills_and_repeat_poll_does_not_double_count(self):
        # 加強：時間戳在掛單後、較晚才出現在 API 的成交仍計入；重複輪詢不去重失敗
        a = dict(tr("Yes", "SELL", 0.29, 4, self.t0 + 3), transaction_hash="0xc", token_id="Y")
        t = sim.apply_fills(self.t, [], BOOK)  # 第一輪 API 還沒有這筆
        self.assertEqual(t["filled_shares"], 0)
        t = sim.apply_fills(t, [a], BOOK)
        self.assertEqual(t["filled_shares"], 4)
        t = sim.apply_fills(t, [a], BOOK)  # 同一筆再出現 → 不重複計
        self.assertEqual(t["filled_shares"], 4)
        self.assertEqual(t["fee_paid"], 0)

    def test_rescan_before_settle_picks_up_late_trade_after_cancel(self):
        from unittest import mock
        t = dict(self.t, cancel_at_epoch=self.t0 + 5)
        later = common.now_utc() + timedelta(seconds=10)
        t = sim.apply_fills(t, [], BOOK, now=later)
        self.assertEqual(t["status"], "cancelled")
        late = dict(tr("Yes", "SELL", 0.20, 10, self.t0 + 2), transaction_hash="0xd", token_id="Y")
        seen = []
        def fake(cid, since, **kw):
            seen.append(since)
            return [late]
        with mock.patch.object(sim, "fetch_trades", fake):
            t2, ok = sim.rescan_before_settle(t, now=later)
        self.assertTrue(ok)
        self.assertEqual(seen, [t["placed_at"]["epoch"]])
        self.assertEqual(t2["filled_shares"], 10)
        self.assertEqual(t2["status"], "filled")

    def test_rescan_before_settle_fetch_failure_does_not_settle_cancel(self):
        from unittest import mock
        t = dict(self.t, cancel_at_epoch=self.t0 + 5)
        later = common.now_utc() + timedelta(seconds=10)
        t = sim.apply_fills(t, [], BOOK, now=later)
        self.assertEqual(t["status"], "cancelled")
        before = t["last_checked_epoch"]
        with mock.patch.object(sim, "fetch_trades", side_effect=RuntimeError("boom")):
            t2, ok = sim.rescan_before_settle(t, now=later)
        self.assertFalse(ok)
        self.assertEqual(t2["status"], "cancelled")
        self.assertEqual(t2["filled_shares"], 0)
        self.assertEqual(t2["last_checked_epoch"], before)

    def test_check_all_at_cancel_fetches_from_placed_and_applies_late_trade(self):
        from unittest import mock
        self.t["cancel_at_epoch"] = self.t0 + 1
        sim.write_json(sim.ticket_path(self.t["id"]), self.t)
        late = dict(tr("Yes", "SELL", 0.20, 7, self.t0 + 0.5), transaction_hash="0xe", token_id="Y")
        seen = []
        def fake(cid, since, **kw):
            seen.append(since)
            return [late]
        with mock.patch.object(sim, "now_utc", return_value=common.now_utc() + timedelta(seconds=10)):
            with mock.patch.object(sim, "fetch_trades", fake):
                out = sim.check_all({})
        self.assertEqual(seen, [self.t["placed_at"]["epoch"]])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["filled_shares"], 7)
        self.assertIn(out[0]["status"], ("partial", "partial_cancelled"))

    def test_trades_after_cancel_time_ignored(self):
        t = dict(self.t, cancel_at_epoch=self.t0 + 5)
        t = sim.apply_fills(t, [tr("Yes", "SELL", 0.20, 10, self.t0 + 6)], BOOK)
        self.assertEqual(t["filled_shares"], 0)

    def test_check_all_trade_api_failure_does_not_advance(self):
        from unittest import mock
        before = sim.open_tickets()[0]["last_checked_epoch"]
        with mock.patch.object(sim, "fetch_trades", side_effect=RuntimeError("boom")):
            self.assertEqual(sim.check_all({}), [])
        t = sim.open_tickets()[0]
        self.assertEqual(t["last_checked_epoch"], before)
        self.assertEqual(t["status"], "open")
        self.assertIn("boom", t["errors"][0])

    def test_fetch_trades_pagination_keeps_condition(self):
        from unittest import mock
        seen = []
        pages = [{"data": [{"condition_id": "0xc", "timestamp": 100}, {"condition_id": "0xc", "timestamp": 90}],
                  "pagination": {"next_cursor": "c1"}},
                 {"data": [{"condition_id": "0xc", "timestamp": 80}, {"condition_id": "0xOTHER", "timestamp": 70}],
                  "pagination": {"next_cursor": None}}]
        def fake(url, params=None, **kw):
            seen.append(dict(params))
            return pages[len(seen) - 1]
        with mock.patch.object(sim, "get_json", fake):
            out = sim.fetch_trades("0xc", 0)
        self.assertTrue(all(p["condition"] == "0xc" for p in seen))
        self.assertEqual(seen[1]["cursor"], "c1")
        self.assertEqual([r["timestamp"] for r in out], [100, 90, 80])

    def test_cancel_before_expiry(self):
        t = dict(self.t, cancel_at_epoch=self.t0 + 5)
        t = sim.apply_fills(t, [], BOOK, now=common.now_utc() + timedelta(seconds=10))
        self.assertEqual(t["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()

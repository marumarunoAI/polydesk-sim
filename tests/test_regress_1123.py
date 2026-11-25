"""2026-11-23 驗收退件的回歸測試：
1) S1 標籤卻買 NO、journal edge 為負仍 TRADE；2) 剛上架市場 window_extremes 誤判 unavailable。"""
import unittest
from datetime import datetime, timezone
from unittest import mock

import quant
import run_day
import strategies as st

# 11/23 實際那一筆：will-bitcoin-dip-to-45k-in-november-2026
ROW_45K = {"slug": "will-bitcoin-dip-to-45k-in-november-2026", "asset": "BTC", "kind": "reach",
           "direction": "down", "level": 45000.0, "tick_size": 0.001, "min_order_size": 5,
           "end_utc": "2026-12-01T05:00:00Z",
           "yes_book": {"best_bid": 0.025, "best_ask": 0.026, "mid": 0.0255}}
FAIR_45K = {"fair_yes": 3.6e-05, "inputs_unavailable": [], "fomc_in_window": False, "spot": 61721.0}
NOW = datetime(2026, 11, 23, 5, 48, 46, tzinfo=timezone.utc)


def _ev(clusters, funding=0.0001):
    return {"assets": {"BTC": {"liquidation_clusters": {"value": clusters},
                               "binance_funding": {"value": funding}}},
            "global": {}}


class S1DirectionTest(unittest.TestCase):
    def test_1123_row_s1_no_longer_trades_no(self):
        d = st.decide_s1(FAIR_45K, ROW_45K, _ev([{"price": 60000, "usd": 1.432e9}]), NOW)
        self.assertEqual(d["side"], "YES")
        self.assertNotEqual(d["decision"], "TRADE")
        self.assertLess(d["edge"], 0)

    def test_1123_row_belongs_to_s2_with_positive_edge(self):
        d = st.decide_s2(FAIR_45K, ROW_45K, _ev([{"price": 60000, "usd": 1.432e9}]), NOW)
        self.assertEqual((d["decision"], d["side"]), ("TRADE", "NO"))
        self.assertGreater(d["edge"], d["threshold"])
        self.assertTrue(run_day.trade_invariants_ok("S2", d))
        lim = st.limit_for("NO", ROW_45K, 1 - FAIR_45K["fair_yes"], d["threshold"])
        self.assertLess(lim, 0.97)   # 規則 5：絕不在 0.97 以上買
        self.assertAlmostEqual(lim, 0.969)

    def test_s1_s2_s3_trade_edge_always_positive_and_above_threshold(self):
        ev3 = {"assets": {"BTC": {"liquidation_clusters": {"value": [{"price": 59000, "usd": 20e9}]},
                                  "binance_funding": {"value": 0.0001}, "binance_oi": {"value": 1.0},
                                  "etf_flow_prev_day": {"value": 100.0}}},
               "global": {"macro_events_next8d": {"value": []}}}
        for q in (0.01, 0.2, 0.5, 0.8, 0.99):
            for mid in (0.02, 0.3, 0.5, 0.7, 0.97):
                row = dict(ROW_45K, direction="up", level=60000.0, end_utc="2099-01-01T00:00:00Z",
                           yes_book={"best_bid": mid - 0.005, "best_ask": mid + 0.005, "mid": mid})
                f = dict(FAIR_45K, fair_yes=q, spot=58000.0)
                for s, fn in (("S1", st.decide_s1), ("S2", st.decide_s2), ("S3", st.decide_s3)):
                    d = fn(f, row, ev3, NOW)
                    if s == "S1":
                        self.assertEqual(d.get("side", "YES"), "YES")
                    if d["decision"] == "TRADE":
                        self.assertGreater(d["edge"], d["threshold"], (s, q, mid, d))
                        self.assertTrue(run_day.trade_invariants_ok(s, d), (s, q, mid, d))

    def test_invariant_guard_blocks_bad_trades(self):
        self.assertFalse(run_day.trade_invariants_ok("S1", {"side": "NO", "edge": 0.03, "threshold": 0.02}))
        self.assertFalse(run_day.trade_invariants_ok("S1", {"side": "YES", "edge": -0.03, "threshold": 0.02}))
        self.assertFalse(run_day.trade_invariants_ok("S3", {"side": "NO", "edge": -0.0255, "threshold": 0.0202}))
        self.assertFalse(run_day.trade_invariants_ok("S2", {"side": "YES", "edge": 0.05, "threshold": 0.02}))
        self.assertTrue(run_day.trade_invariants_ok("S3", {"side": "NO", "edge": 0.03, "threshold": 0.02}))


def _fake_binance(candles):
    """candles: {interval: [(open_ms, high, low)]}；照 Binance 規則只回 open ≥ startTime 且 ≤ endTime。"""
    def get_json(url, params=None, **kw):
        out = []
        for t, h, l in candles.get(params["interval"], []):
            if t >= params["startTime"] and t <= params.get("endTime", 1 << 62):
                out.append([t, "0", str(h), str(l), "0"])
        return out[:params["limit"]]
    return get_json


class WindowExtremesTest(unittest.TestCase):
    def setUp(self):
        quant._EXT.clear()

    def test_listed_48min_ago_not_unavailable(self):
        # 11/23 實況：上架 05:00:17Z、13:48 台北跑；1h K 的 startTime=05:00:17 回空 → 以前變 unavailable
        start = datetime(2026, 11, 23, 5, 0, 17, tzinfo=timezone.utc)
        h05 = int(datetime(2026, 11, 23, 5, tzinfo=timezone.utc).timestamp() * 1000)
        mins = [(h05 + i * 60000, 61800 + i, 61700 - i) for i in range(49)]
        fake = _fake_binance({"1h": [(h05, 61900, 61600)], "1m": mins})
        with mock.patch.object(quant, "get_json", fake):
            hi, lo = quant.extremes_since("BTC", start, NOW)
        self.assertEqual((hi, lo), (61848, 61652))
        b = {"slug": "x", "kind": "reach", "asset": "BTC", "direction": "down", "level": 61000.0,
             "end_utc": "2026-11-30T05:00:00Z", "start_utc": "2026-11-23T05:00:17Z"}
        inp = {"spot": 61721.0, "realized_vol": 0.5, "daily": [], "source": "t", "ts": {}}
        quant._EXT.clear()
        with mock.patch.object(quant, "get_json", fake):
            f = quant.price_one(b, inp, None, [], NOW)
        self.assertNotIn("window_extremes", f["inputs_unavailable"])
        self.assertLess(f["fair_yes"], 1.0)

    def test_first_partial_hour_counts_for_touch(self):
        # 上架 05:30:10，05:40 已跌破關卡，之後都在上面；舊做法從 06:00 起算會漏掉
        start = datetime(2026, 11, 22, 5, 30, 10, tzinfo=timezone.utc)
        h05 = int(datetime(2026, 11, 22, 5, tzinfo=timezone.utc).timestamp() * 1000)
        mins = [(h05 + i * 60000, 62000, 60900 if i == 40 else 61500) for i in range(60)]
        hours = [(h05 + i * 3600000, 62000, 61500) for i in range(1, 24)]
        with mock.patch.object(quant, "get_json", _fake_binance({"1m": mins, "1h": hours})):
            hi, lo = quant.extremes_since("BTC", start, NOW)
        self.assertEqual(lo, 60900)

    def test_genuine_api_failure_still_unavailable(self):
        b = {"slug": "x", "kind": "reach", "asset": "BTC", "direction": "down", "level": 61000.0,
             "end_utc": "2026-11-30T05:00:00Z", "start_utc": "2026-11-23T05:00:17Z"}
        inp = {"spot": 61721.0, "realized_vol": 0.5, "daily": [], "source": "t", "ts": {}}
        def boom(*a, **k):
            raise ConnectionError("451")
        with mock.patch.object(quant, "get_json", boom):
            f = quant.price_one(b, inp, None, [], NOW)
        self.assertIn("window_extremes", f["inputs_unavailable"])   # 規則 6 不放寬
        d = st.decide_s1(f, ROW_45K, _ev([]), NOW)
        self.assertEqual(d["decision"], "SKIP")

    def test_empty_response_is_unavailable_not_crash(self):
        start = datetime(2026, 11, 23, 5, 0, 17, tzinfo=timezone.utc)
        with mock.patch.object(quant, "get_json", _fake_binance({})):
            self.assertIsNone(quant.extremes_since("BTC", start, NOW))


if __name__ == "__main__":
    unittest.main()

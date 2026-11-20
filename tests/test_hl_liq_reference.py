import os
import unittest
from unittest import mock

from helpers import TempDirs  # noqa: F401
import hl_liq_reference as hl
import strategies


class FakeResp:
    def __init__(self, code, js=None, headers=None):
        self.status_code, self._js, self.headers = code, js, headers or {}

    def json(self):
        return self._js


class FakeSession:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = 0

    def post(self, url, json=None, timeout=None):
        self.calls += 1
        c = self.codes.pop(0) if self.codes else 200
        return FakeResp(c, {"ok": 1}, {"Retry-After": "7"} if c == 429 else {})


class ThrottleTest(unittest.TestCase):
    def mk(self, **kw):
        self.sleeps = []
        t = [0.0]

        def sl(x):
            self.sleeps.append(x)
            t[0] += x
        return hl.Throttle(sleep=sl, clock=lambda: t[0], **kw)

    def test_min_interval_enforced_between_requests(self):
        th = self.mk(min_interval=0.5)
        s = FakeSession([])
        th.post(s, "u", {})
        th.post(s, "u", {})
        self.assertTrue(any(abs(x - 0.5) < 1e-9 for x in self.sleeps))

    def test_429_retries_with_retry_after_then_succeeds(self):
        th = self.mk()
        s = FakeSession([429, 429, 200])
        self.assertEqual(th.post(s, "u", {}), {"ok": 1})
        self.assertEqual(s.calls, 3)
        self.assertEqual(th.stats["http_429"], 2)
        self.assertIn(7.0, self.sleeps)           # 尊重 Retry-After
        self.assertGreater(th.interval, th.min_interval)  # 被限流後自動放慢

    def test_gives_up_after_max_retries(self):
        th = self.mk(max_retries=2)
        s = FakeSession([429] * 10)
        with self.assertRaises(RuntimeError):
            th.post(s, "u", {})
        self.assertEqual(s.calls, 3)

    def test_non_retryable_4xx_raises_immediately(self):
        th = self.mk()
        s = FakeSession([404])
        with self.assertRaises(RuntimeError):
            th.post(s, "u", {})
        self.assertEqual(s.calls, 1)


class DistributionTest(unittest.TestCase):
    def test_buckets_and_sides(self):
        pos = [{"coin": "BTC", "szi": 1.0, "val": 100.0, "liq": 90.0},    # 多單，-10%
               {"coin": "BTC", "szi": -1.0, "val": 50.0, "liq": 102.0},   # 空單，+2%
               {"coin": "BTC", "szi": 1.0, "val": 30.0, "liq": None},     # cross，無清算價
               {"coin": "ETH", "szi": 1.0, "val": 10.0, "liq": 1.0}]
        d = hl.distribution(pos, {"BTC": 100.0, "ETH": 2.0}, {"BTC": 10.0, "ETH": 1.0})["BTC"]
        self.assertEqual(d["positions"], 3)
        self.assertEqual(d["with_liq_px"], 2)
        self.assertEqual(d["no_liq_px"], 1)
        self.assertEqual(d["long_liq_notional_usd"], 100.0)
        self.assertEqual(d["short_liq_notional_usd"], 50.0)
        self.assertEqual(d["liq_within_pct_notional_usd"]["±3%"], 50.0)
        self.assertEqual(d["liq_within_pct_notional_usd"]["±10%"], 150.0)
        self.assertAlmostEqual(d["coverage_of_oi"], 180.0 / 1000.0, places=4)
        b = {(x["from_pct"], x["to_pct"]): x for x in d["buckets_vs_mark"]}
        self.assertEqual(b[(-20, -10)]["notional_usd"] + b[(-10, -5)]["notional_usd"], 100.0)
        self.assertEqual(b[(0, 3)]["notional_usd"], 50.0)


class ScanTest(unittest.TestCase):
    def test_scan_marks_reference_only_and_tolerates_account_failures(self):
        rows = [{"ethAddress": "0xa", "accountValue": "2"}, {"ethAddress": "0xb", "accountValue": "1"}]

        class S:
            def post(self, url, json=None, timeout=None):
                if json["type"] == "metaAndAssetCtxs":
                    return FakeResp(200, [{"universe": [{"name": "BTC"}, {"name": "ETH"}]},
                                          [{"markPx": "100", "openInterest": "10"}, {"markPx": "2", "openInterest": "5"}]])
                if json["user"] == "0xb":
                    return FakeResp(404)
                return FakeResp(200, {"assetPositions": [{"position": {"coin": "BTC", "szi": "1", "positionValue": "100", "liquidationPx": "80"}}]})
        th = hl.Throttle(min_interval=0, sleep=lambda x: None)
        r = hl.scan(10, th, S(), leaderboard=rows)
        self.assertTrue(r["reference_only"])
        self.assertEqual((r["accounts_ok"], r["accounts_failed"]), (1, 1))
        self.assertEqual(r["value"]["BTC"]["long_liq_notional_usd"], 100.0)
        self.assertIn("utc", r["fetched_at"])
        self.assertIn("hyperliquid", r["source"])

    def test_scan_total_failure_is_unavailable(self):
        class S:
            def post(self, *a, **k):
                return FakeResp(500)
        th = hl.Throttle(min_interval=0, max_retries=1, sleep=lambda x: None)
        r = hl.scan(5, th, S(), leaderboard=[{"ethAddress": "0xa", "accountValue": "1"}])
        self.assertEqual(r["value"], "unavailable")
        self.assertIn("reason", r)


class NotAnSignalTest(unittest.TestCase):
    def test_no_strategy_or_risk_code_reads_the_reference(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fn in ("strategies.py", "risk_gate.py", "quant.py", "sim.py", "exits.py", "gate.py"):
            with open(os.path.join(root, fn), encoding="utf-8") as fh:
                txt = fh.read()
            for needle in ("hl_liq", "hl_liquidation", "hl_liquidation_distribution"):
                self.assertNotIn(needle, txt, f"{fn} 不得讀 {needle}")

    def test_liquidation_clusters_still_unavailable_and_reference_does_not_change_decision(self):
        v = strategies.liq_clusters_value({"liquidation_clusters": {"value": "unavailable", "reason": "none"}})
        self.assertEqual(v[0], "unavailable")
        ev_with = {"reference": {"hl_liquidation_distribution": {"value": {"BTC": {"long_liq_notional_usd": 9e12}}}},
                   "liquidation_clusters": {"value": "unavailable", "reason": "none"}}
        self.assertEqual(strategies.liq_clusters_value(ev_with)[0], "unavailable")

    def test_evidence_collect_never_fills_liquidation_clusters(self):
        import inspect
        import evidence
        src = inspect.getsource(evidence.collect)
        self.assertIn('"liquidation_clusters": na(', src)

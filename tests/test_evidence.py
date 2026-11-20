import unittest
from unittest import mock

from helpers import TempDirs  # noqa: F401
import common
import evidence


class EvidenceParseTest(unittest.TestCase):
    def test_okx_funding_converted_to_8h(self):
        calls = iter([
            {"data": [{"fundingRate": "0.0001", "fundingTime": "0", "nextFundingTime": str(4 * 3600 * 1000)}]},
            {"data": [{"oiCcy": "123.5", "oiUsd": "9999"}]}])
        with mock.patch.object(evidence, "get_json", lambda *a, **k: next(calls)):
            f, o = evidence.okx("BTC")
        self.assertAlmostEqual(f["value"], 0.0002)  # 4h 週期 → ×2 到 8h
        self.assertEqual(o["value"], 123.5)
        self.assertIn("okx.com", f["source"])
        self.assertIn("utc", f["fetched_at"])

    def test_etf_incomplete_is_unavailable(self):
        data = {"data": {"IBIT": {"dt": "2026-11-19", "change": -5, "error": False},
                         "FBTC": {"dt": "2026-11-18", "change": -1, "error": False}}, "batch_ts": "x"}
        fixed = common.now_utc().replace(year=2026, month=11, day=20, hour=5)
        with mock.patch.object(evidence, "get_json", lambda *a, **k: data), \
                mock.patch("common.now_utc", lambda: fixed):
            with self.assertRaises(RuntimeError) as cm:
                evidence.btc_etf_prev_day()
        self.assertIn("FBTC", str(cm.exception))

    def test_etf_complete_sums(self):
        data = {"data": {"IBIT": {"dt": "2026-11-19", "change": -5, "error": False},
                         "FBTC": {"dt": "2026-11-19", "change": 2, "error": False}}, "batch_ts": "x"}
        fixed = common.now_utc().replace(year=2026, month=11, day=20, hour=5)
        with mock.patch.object(evidence, "get_json", lambda *a, **k: data), \
                mock.patch("common.now_utc", lambda: fixed):
            r = evidence.btc_etf_prev_day()
        self.assertEqual(r["value"], -3)
        self.assertEqual(r["trading_day"], "2026-11-19")

    def test_eth_etf_unavailable(self):
        with self.assertRaises(RuntimeError):
            evidence.etf_flow("ETH")

    def test_macro_no_record_is_empty_not_error(self):
        resp = {"data": None, "status": {"bCodeMessage": [{"code": 1002}]}}
        with mock.patch.object(evidence, "get_json", lambda *a, **k: resp):
            r = evidence.macro_events(days=2)
        self.assertEqual(r["value"], [])

    def test_macro_unexpected_response_raises(self):
        with mock.patch.object(evidence, "get_json", lambda *a, **k: {"data": None, "status": {}}):
            with self.assertRaises(RuntimeError):
                evidence.macro_events(days=1)


if __name__ == "__main__":
    unittest.main()

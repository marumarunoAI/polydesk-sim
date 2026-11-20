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


def _v(x, **kw):
    return dict({"value": x}, **kw)


class NewSourcesTest(unittest.TestCase):
    def test_bitget_parse(self):
        calls = iter([
            {"code": "00000", "data": [{"fundingRate": "-0.000031", "fundingRateInterval": "8"}]},
            {"code": "00000", "data": {"openInterestList": [{"symbol": "BTCUSDT", "size": "36855.4"}]}}])
        with mock.patch.object(evidence, "get_json", lambda *a, **k: next(calls)):
            f, o = evidence.bitget("BTC")
        self.assertAlmostEqual(f["value"], -0.000031)
        self.assertEqual(o["value"], 36855.4)
        self.assertIn("api.bitget.com", f["source"])
        self.assertIn("utc", o["fetched_at"])

    def test_bitget_interval_4h_scaled(self):
        calls = iter([
            {"code": "00000", "data": [{"fundingRate": "0.0001", "fundingRateInterval": "4"}]},
            {"code": "00000", "data": {"openInterestList": [{"size": "1"}]}}])
        with mock.patch.object(evidence, "get_json", lambda *a, **k: next(calls)):
            f, _ = evidence.bitget("ETH")
        self.assertAlmostEqual(f["value"], 0.0002)

    def test_bitget_error_code_raises(self):
        with mock.patch.object(evidence, "get_json", lambda *a, **k: {"code": "40404", "msg": "x"}):
            with self.assertRaises(RuntimeError):
                evidence.bitget("BTC")

    def test_gate_parse_contract_multiplier(self):
        c = {"funding_rate": "-0.0000011", "funding_interval": 28800,
             "position_size": 295372412, "quanto_multiplier": "0.0001"}
        with mock.patch.object(evidence, "get_json", lambda *a, **k: c):
            f, o = evidence.gate("BTC")
        self.assertAlmostEqual(f["value"], -0.0000011)
        self.assertAlmostEqual(o["value"], 29537.2412)
        self.assertIn("api.gateio.ws", o["source"])

    def test_dydx_1h_converted_to_8h(self):
        m = {"markets": {"BTC-USD": {"status": "ACTIVE", "nextFundingRate": "-0.00000578", "openInterest": "194.97"}}}
        with mock.patch.object(evidence, "get_json", lambda *a, **k: m):
            f, o = evidence.dydx("BTC")
        self.assertAlmostEqual(f["value"], -0.00000578 * 8)
        self.assertEqual(o["value"], 194.97)
        self.assertIn("indexer.dydx.trade", f["source"])

    def test_dydx_inactive_raises(self):
        m = {"markets": {"BTC-USD": {"status": "PAUSED", "nextFundingRate": "0", "openInterest": "1"}}}
        with mock.patch.object(evidence, "get_json", lambda *a, **k: m):
            with self.assertRaises(RuntimeError):
                evidence.dydx("BTC")

    def test_collect_failure_marks_unavailable_not_invented(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 451")
        with mock.patch.object(evidence, "bitget", boom), mock.patch.object(evidence, "gate", boom), \
                mock.patch.object(evidence, "dydx", boom), \
                mock.patch.object(evidence, "binance_funding", boom), mock.patch.object(evidence, "binance_oi", boom), \
                mock.patch.object(evidence, "okx", boom), mock.patch.object(evidence, "deribit_perp", boom), \
                mock.patch.object(evidence, "hyperliquid", boom), mock.patch.object(evidence, "deribit_dvol", boom), \
                mock.patch.object(evidence, "etf_flow", boom), mock.patch.object(evidence, "macro_events", boom), \
                mock.patch.object(evidence, "fomc_decision_days", lambda: []):
            ev = evidence.collect()
        a = ev["assets"]["BTC"]
        for k in ("bitget_funding", "bitget_oi", "gate_funding", "gate_oi", "dydx_funding", "dydx_oi"):
            self.assertEqual(a[k]["value"], "unavailable")
            self.assertIn("HTTP 451", a[k]["reason"])


class FundingOrderTest(unittest.TestCase):
    def test_order_includes_new_sources_and_dydx_last(self):
        import strategies
        self.assertEqual(strategies.FUNDING_ORDER[-1], "dydx_funding")
        self.assertEqual(strategies.OI_ORDER[-1], "dydx_oi")
        for n in ("bitget", "gate", "dydx"):
            self.assertIn(f"{n}_funding", strategies.FUNDING_ORDER)
            self.assertIn(f"{n}_oi", strategies.OI_ORDER)

    def test_first_available_falls_through_to_new_sources(self):
        import strategies
        na = _v("unavailable")
        ea = {k: na for k in strategies.FUNDING_ORDER}
        ea["bitget_funding"] = _v(0.0002)
        ea["dydx_funding"] = _v(0.0009)
        self.assertEqual(strategies._funding_8h(ea), (0.0002, "bitget"))
        ea["bitget_funding"] = na
        ea["gate_funding"] = _v(-0.0001)
        self.assertEqual(strategies._funding_8h(ea), (-0.0001, "gate"))
        ea["gate_funding"] = na
        self.assertEqual(strategies._funding_8h(ea), (0.0009, "dydx"))
        ea["dydx_funding"] = na
        self.assertEqual(strategies._funding_8h(ea)[0], "unavailable")

    def test_earlier_source_wins_over_new(self):
        import strategies
        ea = {"binance_funding": _v(0.0001), "bitget_funding": _v(0.5)}
        self.assertEqual(strategies._funding_8h(ea), (0.0001, "binance"))

    def test_oi_fallthrough(self):
        import strategies
        na = _v("unavailable")
        ea = {k: na for k in strategies.OI_ORDER}
        ea["gate_oi"] = _v(29000.0)
        self.assertEqual(strategies._oi(ea), (29000.0, "gate"))
        ea["gate_oi"] = na
        ea["dydx_oi"] = _v(195.0)
        self.assertEqual(strategies._oi(ea), (195.0, "dydx"))

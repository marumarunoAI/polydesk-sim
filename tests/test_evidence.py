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

    def test_etf_flow_uses_farside_not_btcetfdata(self):
        html = _fx("farside_btc_ok.html")
        fixed = common.now_utc().replace(year=2026, month=11, day=20, hour=14, minute=35)
        def boom(*a, **k):
            raise AssertionError("btcetfdata should not be consulted for etf_flow")
        with mock.patch.object(evidence, "btc_etf_prev_day", boom),                 mock.patch.object(evidence, "fetch_farside_html", lambda url: html),                 mock.patch("common.now_utc", lambda: fixed):
            r = evidence.etf_flow("BTC")
        self.assertEqual(r["trading_day"], "2026-11-19")
        self.assertEqual(r["unit"], "US$m")
        self.assertIn("farside.co.uk/btc", r["source"])

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


class OkxPremarketTest(unittest.TestCase):
    INS = {"code": "0", "data": [
        {"instId": "AAA-USDT-SWAP", "ruleType": "pre_market", "state": "live", "listTime": "1", "ctVal": "1", "ctValCcy": "AAA", "settleCcy": "USDT"},
        {"instId": "BTC-USDT-SWAP", "ruleType": "normal", "state": "live"},
        {"instId": "BBB-USDT-SWAP", "ruleType": "pre_market", "state": "live", "listTime": "2"}]}

    def _fake(self, fail_bbb=False):
        def f(url, **k):
            if "instruments" in url:
                return self.INS
            if "BBB" in url and fail_bbb:
                raise RuntimeError("HTTP 500")
            return {"code": "0", "data": [{"last": "12.5", "bidPx": "12.4", "askPx": "12.6", "vol24h": "9", "ts": "1795"}]}
        return f

    def test_only_pre_market_listed_with_source_and_time(self):
        with mock.patch.object(evidence, "get_json", self._fake()):
            r = evidence.okx_premarket()
        ids = [x["instId"] for x in r["value"]]
        self.assertEqual(ids, ["AAA-USDT-SWAP", "BBB-USDT-SWAP"])
        self.assertEqual(r["value"][0]["last"], 12.5)
        self.assertIn("ticker?instId=AAA", r["value"][0]["source"])
        self.assertIn("utc", r["value"][0]["fetched_at"])
        self.assertTrue(r["reference_only"])

    def test_single_ticker_failure_marks_only_that_one(self):
        with mock.patch.object(evidence, "get_json", self._fake(fail_bbb=True)):
            r = evidence.okx_premarket()
        self.assertEqual(r["value"][0]["last"], 12.5)
        self.assertEqual(r["value"][1]["last"], "unavailable")
        self.assertIn("HTTP 500", r["value"][1]["reason"])

    def test_instruments_failure_raises(self):
        with mock.patch.object(evidence, "get_json", lambda *a, **k: {"code": "50000", "msg": "x"}):
            with self.assertRaises(RuntimeError):
                evidence.okx_premarket()

    def test_not_wired_into_strategies(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fn in ("strategies.py", "risk_gate.py", "quant.py", "sim.py", "exits.py", "run_day.py"):
            with open(os.path.join(root, fn), encoding="utf-8") as fh:
                self.assertNotIn("okx_premarket", fh.read(), fn)


def _fx(name):
    import os
    path = os.path.join(os.path.dirname(__file__), "fixtures", name)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _resp(status, text="", headers=None):
    r = mock.Mock()
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    return r


class FarsideEtfTest(unittest.TestCase):
    def _now(self, y=2026, m=11, d=20, h=14, mi=35):
        return common.now_utc().replace(year=y, month=m, day=d, hour=h, minute=mi)

    def test_success_real_html_ignores_today_dashes(self):
        """真實頁面：當天（20 Nov）各基金為 '-'，前一交易日 19 Nov 已齊，應可用。"""
        r = evidence.farside_etf_prev_day("BTC", html=_fx("farside_btc_ok.html"), now=self._now())
        self.assertEqual(r["value"], -582.3)
        self.assertEqual(r["trading_day"], "2026-11-19")
        self.assertEqual(r["data_date"], "2026-11-19")
        self.assertEqual(r["unit"], "US$m")
        self.assertEqual(r["source"], evidence.FARSIDE["BTC"])
        self.assertIn("utc", r["fetched_at"])
        self.assertIn("taipei", r["fetched_at"])
        self.assertEqual(r["funds"]["IBIT"], -541.1)
        self.assertEqual(r["funds"]["BTCW"], 0.3)
        self.assertEqual(r["funds"]["MSBT"], 49.6)
        self.assertEqual(len(r["funds"]), 12)

    def test_success_eth_real_html(self):
        r = evidence.farside_etf_prev_day("ETH", html=_fx("farside_eth_ok.html"), now=self._now())
        self.assertEqual(r["value"], -131.2)
        self.assertEqual(r["trading_day"], "2026-11-19")
        self.assertEqual(r["funds"]["ETHA"], -124.2)
        self.assertEqual(r["funds"]["ETHE"], -5.2)
        self.assertEqual(r["source"], evidence.FARSIDE["ETH"])

    def test_passed_page_with_cdn_cgi_script_is_not_challenge(self):
        """成功頁常帶 /cdn-cgi/challenge-platform/... 腳本，不得因此標 unavailable。"""
        html = _fx("farside_btc_ok.html").replace(
            "</head>",
            "<script src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'></script></head>",
            1)
        self.assertFalse(evidence._is_cloudflare_challenge(200, {"server": "cloudflare"}, html))
        r = evidence.farside_etf_prev_day("BTC", html=html, now=self._now())
        self.assertEqual(r["value"], -582.3)

    def test_prev_day_dashes_unavailable(self):
        with self.assertRaises(RuntimeError) as cm:
            evidence.farside_etf_prev_day(
                "BTC", html=_fx("farside_btc_prev_day_dash.html"), now=self._now())
        msg = str(cm.exception)
        self.assertIn("2026-11-19", msg)
        self.assertIn("IBIT", msg)
        self.assertIn("Total", msg)

    def test_http_403_unavailable(self):
        with mock.patch.object(evidence._S, "get", lambda *a, **k: _resp(403, "Forbidden")):
            with self.assertRaises(RuntimeError) as cm:
                evidence.fetch_farside_html(evidence.FARSIDE["BTC"])
        self.assertIn("403", str(cm.exception))
        self.assertIn("Cloudflare", str(cm.exception))

    def test_challenge_page_unavailable(self):
        html = _fx("farside_challenge.html")
        with self.assertRaises(RuntimeError) as cm:
            evidence.farside_etf_prev_day("BTC", html=html, now=self._now())
        self.assertIn("challenge", str(cm.exception).lower())
        with mock.patch.object(evidence._S, "get",
                               lambda *a, **k: _resp(403, html, {"cf-mitigated": "challenge"})):
            with self.assertRaises(RuntimeError) as cm:
                evidence.etf_flow("ETH")
        self.assertIn("403", str(cm.exception))

    def test_non_200_unavailable(self):
        with mock.patch.object(evidence._S, "get", lambda *a, **k: _resp(503, "nope")):
            with self.assertRaises(RuntimeError) as cm:
                evidence.fetch_farside_html(evidence.FARSIDE["ETH"])
        self.assertIn("503", str(cm.exception))

    def test_parentheses_negative_and_thousands(self):
        self.assertEqual(evidence.parse_farside_number("(541.1)"), ("value", -541.1))
        self.assertEqual(evidence.parse_farside_number("(1,023.4)"), ("value", -1023.4))
        self.assertEqual(evidence.parse_farside_number("1,119.9"), ("value", 1119.9))
        self.assertEqual(evidence.parse_farside_number("-"), ("dash", None))
        self.assertEqual(evidence.parse_farside_number(""), ("dash", None))
        now = self._now(d=19, h=10, mi=0)  # 19 Nov 10:00 UTC = 05:00 ET, prev=18 Nov
        r = evidence.farside_etf_prev_day("BTC", html=_fx("farside_missing_cell.html"), now=now)
        self.assertEqual(r["value"], -9.5)
        self.assertEqual(r["funds"], {"IBIT": -12.5, "FBTC": 3.0})

    def test_missing_total_column(self):
        with self.assertRaises(RuntimeError) as cm:
            evidence.farside_etf_prev_day("BTC", html=_fx("farside_missing_total.html"), now=self._now())
        self.assertIn("Total", str(cm.exception))

    def test_missing_cell_on_prev_day(self):
        with self.assertRaises(RuntimeError) as cm:
            evidence.farside_etf_prev_day("BTC", html=_fx("farside_missing_cell.html"), now=self._now())
        self.assertIn("Total: missing cell", str(cm.exception))

    def test_collect_records_farside_reason_on_failure(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 403 Cloudflare challenge/block")
        with mock.patch.object(evidence, "bitget", boom), mock.patch.object(evidence, "gate", boom),                 mock.patch.object(evidence, "dydx", boom),                 mock.patch.object(evidence, "binance_funding", boom), mock.patch.object(evidence, "binance_oi", boom),                 mock.patch.object(evidence, "okx", boom), mock.patch.object(evidence, "deribit_perp", boom),                 mock.patch.object(evidence, "hyperliquid", boom), mock.patch.object(evidence, "deribit_dvol", boom),                 mock.patch.object(evidence, "etf_flow", boom), mock.patch.object(evidence, "macro_events", boom),                 mock.patch.object(evidence, "fomc_decision_days", lambda: []):
            ev = evidence.collect()
        btc = ev["assets"]["BTC"]["etf_flow_prev_day"]
        eth = ev["assets"]["ETH"]["etf_flow_prev_day"]
        self.assertEqual(btc["value"], "unavailable")
        self.assertEqual(eth["value"], "unavailable")
        self.assertIn("403", btc["reason"])
        self.assertIn("farside.co.uk/btc", btc["source"])
        self.assertIn("farside.co.uk/eth", eth["source"])

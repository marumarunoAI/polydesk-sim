import os
import unittest
from unittest import mock

from helpers import TempDirs
import board
import common
import evidence
import journal
import quant
import run_day
import settle

BK = {"best_bid": 0.4, "best_ask": 0.44, "mid": 0.42, "bids_top5": [], "asks_top5": [],
      "bid_depth_top5": 0, "ask_depth_top5": 0, "last_trade_price": 0.4}


def mk(slug, kind="above"):
    return {"slug": slug, "market_id": slug, "condition_id": "0x" + slug, "question": slug, "kind": kind,
            "asset": "BTC", "direction": "up", "level": 60000.0, "rules": "r", "resolution_source": "b",
            "start_utc": "2026-01-01T00:00:00Z", "end_utc": "2099-01-01T00:00:00Z",
            "end_taipei": "x", "event_slug": "e", "event_title": "e", "yes_token": "Y" + slug,
            "no_token": "N" + slug, "tick_size": 0.01, "min_order_size": 5, "tags": []}


def fake_quant_run(blinds, **kw):
    """只替第一個市場寫 fair（模擬另一個市場盲算失敗）。"""
    b = blinds[0]
    common.write_json(os.path.join(common.DIRS["fair"], f"{b['slug']}.json"),
                      {"slug": b["slug"], "kind": "above", "asset": "BTC", "fair_yes": 0.5, "spot": 61000.0,
                       "end_utc": b["end_utc"], "inputs_unavailable": [], "fomc_in_window": False,
                       "ts": common.stamp(), "date_taipei": common.today_tpe()})
    return 1


def fake_snapshot(markets):
    import time
    time.sleep(1.1)  # board 抓取時間必須晚於 fair
    rows = [dict(m, yes_book=dict(BK), fetched_at_utc="x") for m in markets]
    return {"fetched_at": common.stamp(), "source": [], "counts": {"above_BTC": len(rows)}, "markets": rows}


EV = {"fetched_at": None, "assets": {"BTC": {
    k: {"value": "unavailable", "reason": "t"} for k in
    ("binance_funding", "binance_oi", "hyperliquid_funding", "hyperliquid_oi", "okx_funding", "okx_oi",
     "deribit_funding", "deribit_oi", "etf_flow_prev_day", "liquidation_clusters")}},
    "global": {"macro_events_next8d": {"value": "unavailable"}}}


def fake_collect():
    import time
    ev = dict(EV, fetched_at=common.stamp())
    return ev


class RunDayTest(unittest.TestCase):
    def patches(self):
        return [mock.patch.object(board, "scan_markets", lambda: ([mk("a"), mk("b")], {"events": 1, "excluded_short": 0, "excluded_banned": 0})),
                mock.patch.object(quant, "run", fake_quant_run),
                mock.patch.object(board, "snapshot", fake_snapshot),
                mock.patch.object(evidence, "collect", fake_collect),
                mock.patch.object(settle, "run", lambda: 0)]

    def run_it(self, argv):
        ps = self.patches()
        for p in ps:
            p.start()
        try:
            return run_day.main(argv)
        finally:
            for p in ps:
                p.stop()

    def test_gate_rejection_is_logged_and_day_continues(self):
        with TempDirs():
            self.run_it([])
            rows = journal.load()
            by = {r["market_slug"]: r for r in rows}
            self.assertEqual(set(by), {"a", "b"})
            self.assertTrue(by["b"]["reason"].startswith("gate rejected"))  # 沒有 fair → 拒絕
            self.assertEqual(by["b"]["decision"], "SKIP")
            self.assertNotIn("gate", by["a"]["reason"])

    def test_rerun_is_idempotent(self):
        with TempDirs():
            self.run_it([])
            n = len(journal.load())
            self.run_it([])
            self.assertEqual(len(journal.load()), n)

    def test_dry_run_leaves_real_state_untouched(self):
        with TempDirs():
            self.run_it(["--dry-run"])
            self.assertEqual(journal.load(), [])
            self.assertEqual(os.listdir(common.DIRS["fair"]), [])
            self.assertEqual(os.listdir(common.DIRS["tickets"]), [])

    def test_outdir(self):
        import tempfile
        with TempDirs():
            out = tempfile.mkdtemp()
            self.run_it(["--outdir", out])
            self.assertTrue(os.path.exists(os.path.join(out, "journal", "journal.csv")))
            self.assertEqual(journal.load(), [])


if __name__ == "__main__":
    unittest.main()

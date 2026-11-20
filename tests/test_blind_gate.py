import ast
import os
import unittest
from datetime import timedelta

from helpers import TempDirs  # noqa: F401  (sets sys.path)
import blind
import common
import gate

MKT = {"slug": "will-bitcoin-reach-70k", "question": "Will Bitcoin reach $70,000 in November?",
       "kind": "reach", "asset": "BTC", "direction": "up", "level": 70000.0,
       "rules": "rule text", "resolution_source": "binance", "end_utc": "2026-12-01T05:00:00Z",
       "yes_token": "1", "no_token": "2",
       "yes_book": {"mid": 0.3}, "outcomePrices": "[0.3,0.7]", "bestBid": 0.29}


def write_fair(slug, dt):
    common.write_json(os.path.join(common.DIRS["fair"], f"{slug}.json"),
                      {"slug": slug, "fair_yes": 0.2, "ts": common.stamp(dt)})


def write_board(dt):
    common.write_json(os.path.join(common.DIRS["board"], "latest.json"),
                      {"fetched_at": common.stamp(dt), "markets": [dict(MKT)]})


class BlindTest(unittest.TestCase):
    def test_blind_has_no_prices(self):
        with TempDirs():
            blind.write_blind([MKT])
            b = blind.load_blind()[0]
            for k in b:
                self.assertFalse(any(w in k.lower() for w in blind.PRICE_WORDS), k)
            self.assertNotIn("yes_book", b)
            self.assertNotIn("0.3", str(b))

    def test_quant_never_touches_board_or_evidence(self):
        with open(os.path.join(os.path.dirname(gate.__file__), "quant.py")) as f:
            src = f.read()
        mods = {n.module if isinstance(n, ast.ImportFrom) else a.name
                for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in (n.names if isinstance(n, ast.Import) else [n])}
        self.assertFalse(mods & {"board", "gate", "evidence", "sim"}, mods)
        self.assertNotIn('DIRS["board"]', src)
        self.assertNotIn('DIRS["evidence"]', src)


class GateTest(unittest.TestCase):
    def test_no_fair_rejects_board_read(self):
        with TempDirs():
            write_board(common.now_utc())
            with self.assertRaises(gate.BlindOrderError):
                gate.read_board(MKT["slug"])

    def test_no_fair_rejects_evidence_read(self):
        with TempDirs():
            common.write_json(os.path.join(common.DIRS["evidence"], "latest.json"),
                              {"fetched_at": common.stamp()})
            with self.assertRaises(gate.BlindOrderError):
                gate.read_evidence(MKT["slug"])

    def test_board_fetched_before_fair_rejected(self):
        with TempDirs():
            now = common.now_utc()
            write_board(now - timedelta(minutes=5))
            write_fair(MKT["slug"], now - timedelta(minutes=1))
            with self.assertRaises(gate.BlindOrderError):
                gate.read_board(MKT["slug"])

    def test_fair_in_future_rejected(self):
        with TempDirs():
            now = common.now_utc()
            write_fair(MKT["slug"], now + timedelta(minutes=5))
            write_board(now + timedelta(minutes=6))
            with self.assertRaises(gate.BlindOrderError):
                gate.read_board(MKT["slug"])

    def test_fair_then_board_allowed(self):
        with TempDirs():
            now = common.now_utc()
            write_fair(MKT["slug"], now - timedelta(minutes=2))
            write_board(now - timedelta(minutes=1))
            fair, row = gate.read_board(MKT["slug"])
            self.assertEqual(row["yes_book"]["mid"], 0.3)


class QuantMathTest(unittest.TestCase):
    def test_formulas(self):
        import quant
        self.assertEqual(quant.touch_prob(100, 90, 0.5, 0.1, "up"), 1.0)
        t = quant.touch_prob(100, 110, 0.5, 0.1, "up")
        a = quant.above_prob(100, 110, 0.5, 0.1)
        self.assertTrue(0 < a < t < 1)
        self.assertAlmostEqual(t / a, 2.0, delta=0.4)  # 鏡像：hit ≈ 2 × above


if __name__ == "__main__":
    unittest.main()

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
        self.commits = []
        ps = self.patches() + [mock.patch.object(run_day, "commit_state", lambda day, **k: self.commits.append(day))]
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

    def test_commit_only_for_real_run_not_dry_run_or_outdir(self):
        import tempfile
        with TempDirs():
            self.run_it(["--dry-run"])
            self.assertEqual(self.commits, [])
            self.run_it(["--outdir", tempfile.mkdtemp()])
            self.assertEqual(self.commits, [])
            self.run_it([])
            self.assertEqual(self.commits, [common.today_tpe()])

    def test_outdir(self):
        import tempfile
        with TempDirs():
            out = tempfile.mkdtemp()
            self.run_it(["--outdir", out])
            self.assertTrue(os.path.exists(os.path.join(out, "journal", "journal.csv")))
            self.assertEqual(journal.load(), [])


def _git(repo, *a):
    import subprocess
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)


class CommitStateTest(unittest.TestCase):
    def setUp(self):
        import shutil
        import subprocess
        import tempfile
        self.root = tempfile.mkdtemp()
        self.remote = os.path.join(self.root, "remote.git")
        self.repo = os.path.join(self.root, "work")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.remote], check=True)
        subprocess.run(["git", "clone", "-q", self.remote, self.repo], check=True, capture_output=True)
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".gitignore"),
                    os.path.join(self.repo, ".gitignore"))
        for d in ("journal", "fair", "tickets/test", "board", "evidence"):
            os.makedirs(os.path.join(self.repo, d))
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-qm", "init")
        _git(self.repo, "push", "-q", "-u", "origin", "HEAD:main")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def w(self, rel, txt="x"):
        with open(os.path.join(self.repo, rel), "w") as f:
            f.write(txt)

    def count(self):
        return int(_git(self.repo, "rev-list", "--count", "HEAD").stdout)

    def test_commits_state_dirs_with_fixed_message_and_pushes(self):
        self.w("journal/journal.csv", "a,b\n")
        self.w("fair/m.json", "{}")
        self.w("tickets/t1.json", "{}")
        self.assertEqual(run_day.commit_state("2026-11-20", repo=self.repo), "committed")
        self.assertEqual(_git(self.repo, "log", "-1", "--format=%s").stdout.strip(), "run_day 2026-11-20")
        files = _git(self.repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(sorted(files), ["fair/m.json", "journal/journal.csv", "tickets/t1.json"])
        self.assertEqual(_git(self.repo, "rev-parse", "HEAD").stdout,
                         _git(self.remote, "rev-parse", "main").stdout)  # 已 push

    def test_snapshots_and_test_tickets_are_not_committed(self):
        self.w("journal/journal.csv")
        self.w("tickets/test/x.json")
        self.w("board/b.json")
        self.w("evidence/e.json")
        run_day.commit_state("2026-11-20", repo=self.repo)
        files = _git(self.repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(files, ["journal/journal.csv"])

    def test_no_change_no_empty_commit(self):
        self.w("journal/journal.csv")
        run_day.commit_state("2026-11-20", repo=self.repo)
        n = self.count()
        self.assertEqual(run_day.commit_state("2026-11-20", repo=self.repo), "nochange")
        self.assertEqual(self.count(), n)
        self.w("journal/journal.csv", "changed")
        self.assertEqual(run_day.commit_state("2026-11-21", repo=self.repo), "committed")
        self.assertEqual(self.count(), n + 1)

    def test_push_failure_warns_and_does_not_raise(self):
        import io
        from contextlib import redirect_stdout
        _git(self.repo, "remote", "set-url", "origin", os.path.join(self.root, "nope.git"))
        self.w("journal/journal.csv")
        buf = io.StringIO()
        with redirect_stdout(buf):
            r = run_day.commit_state("2026-11-20", repo=self.repo)
        self.assertEqual(r, "committed")                      # 本機 commit 仍保留
        self.assertIn("警告", buf.getvalue())
        self.assertEqual(_git(self.repo, "log", "-1", "--format=%s").stdout.strip(), "run_day 2026-11-20")

    def test_does_not_sweep_in_other_staged_files(self):
        self.w("other.txt")
        _git(self.repo, "add", "other.txt")
        self.w("journal/journal.csv")
        run_day.commit_state("2026-11-20", repo=self.repo)
        files = _git(self.repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(files, ["journal/journal.csv"])

    def test_not_a_git_dir_is_warning_only(self):
        import tempfile
        self.assertEqual(run_day.commit_state("2026-11-20", repo=tempfile.mkdtemp()), "error")


if __name__ == "__main__":
    unittest.main()

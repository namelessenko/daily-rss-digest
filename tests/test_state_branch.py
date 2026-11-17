"""Exercise real Git persistence and conflict recovery against a local bare remote."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/state_branch.py"


class StateBranchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "source"
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_COMMITTER_NAME="Test",
                        GIT_AUTHOR_EMAIL="test@example.org", GIT_COMMITTER_EMAIL="test@example.org",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.run_cmd(["git", "init", "--bare", str(self.remote)], self.root)
        self.init_repo(self.repo)

    def run_cmd(self, args, cwd, ok=True):
        result = subprocess.run(args, cwd=cwd, env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def init_repo(self, repo):
        self.run_cmd(["git", "init", "-b", "main", str(repo)], self.root)
        self.run_cmd(["git", "remote", "add", "origin", str(self.remote)], repo)
        (repo / "source.txt").write_text("Keep this source file intact\n")
        self.run_cmd(["git", "add", "source.txt"], repo)
        self.run_cmd(["git", "commit", "-m", "Initial source"], repo)

    def action(self, action, repo=None, ok=True):
        return self.run_cmd([sys.executable, str(SCRIPT), action], repo or self.repo, ok)

    def test_initial_save_restore_and_noop_preserve_source_branch(self):
        before = self.run_cmd(["git", "rev-parse", "HEAD"], self.repo).stdout
        self.action("restore")
        path = self.repo / ".digest-data/state.json"
        state = json.loads(path.read_text())
        state["last_checked"] = "2026-11-05T06:17:00+00:00"
        path.write_text(json.dumps(state))
        self.action("save")
        path.unlink()
        self.action("restore")
        self.assertEqual(json.loads(path.read_text()), state)
        self.assertIn("State unchanged", self.action("save").stdout)
        self.assertEqual(before, self.run_cmd(["git", "rev-parse", "HEAD"], self.repo).stdout)
        files = self.run_cmd(["git", "--git-dir", str(self.remote), "ls-tree", "--name-only", "digest-state"], self.root).stdout
        self.assertEqual(files.strip(), "state.json")

    def test_competing_writer_is_rejected_without_overwriting_remote(self):
        self.action("restore")
        self.action("save")
        second = self.root / "second"
        self.init_repo(second)
        self.action("restore", second)
        self.action("restore")
        first_file = self.repo / ".digest-data/state.json"
        data = json.loads(first_file.read_text())
        data["last_checked"] = "2026-11-05T06:17:00+00:00"
        first_file.write_text(json.dumps(data))
        self.action("save")
        second_file = second / ".digest-data/state.json"
        other = json.loads(second_file.read_text())
        other["last_checked"] = "2026-11-06T06:17:00+00:00"
        second_file.write_text(json.dumps(other))
        self.assertNotEqual(self.action("save", second, ok=False).returncode, 0)
        self.action("restore", second)
        self.assertEqual(json.loads(second_file.read_text()), data)

    def test_unreachable_remote_does_not_reset_existing_state(self):
        self.action("restore")
        self.action("save")
        original = (self.repo / ".digest-data/state.json").read_bytes()
        self.run_cmd(["git", "remote", "set-url", "origin", str(self.root / "missing.git")], self.repo)
        self.assertNotEqual(self.action("restore", ok=False).returncode, 0)
        self.assertEqual((self.repo / ".digest-data/state.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

"""Tests for check_done.py, each written against a sentence in README.md or SKILL.md."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_done  # noqa: E402


def run(argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = check_done.main(argv)
    return code, out.getvalue(), err.getvalue()


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name).resolve() / "proj"
        (self.root / "src").mkdir(parents=True)
        self.addCleanup(self._t.cleanup)

    def claim(self, text, *extra):
        return run([text, "--root", str(self.root), *extra])


class Paths(Base):
    def test_existing_file_is_receipt(self):
        """SKILL l.58: a non-empty path that exists is a RECEIPT; claim allowed (exit 0)."""
        (self.root / "src" / "dates.py").write_text("x = 1\n")
        code, out, _ = self.claim("Fixed the date parser in `src/dates.py`")
        self.assertEqual(code, 0, out)
        self.assertIn("RECEIPT", out)
        self.assertNotIn("MISSING", out)

    def test_bare_existing_path_is_receipt(self):
        """README l.6: a claim naming a file that exists is accepted (path not in backticks)."""
        (self.root / "src" / "parse_quotes.py").write_text("x = 1\n")
        code, out, _ = self.claim("Fixed the parser in src/parse_quotes.py")
        self.assertEqual(code, 0, out)

    def test_missing_path_is_missing_and_refused(self):
        """README l.34-37 / SKILL l.63: a named path that does not exist is MISSING and the claim is REFUSED (exit 1)."""
        code, out, _ = self.claim("Fixed the parser in src/parse_quotes.py")
        self.assertEqual(code, 1, out)
        self.assertIn("MISSING", out)
        self.assertIn("REFUSED", out)
        self.assertIn("it names a receipt that does not resolve", out)

    def test_empty_file_is_missing(self):
        """SKILL l.60: an existing file of 0 bytes is MISSING, not a receipt."""
        (self.root / "src" / "empty.py").write_text("")
        code, out, _ = self.claim("Fixed it in `src/empty.py`")
        self.assertEqual(code, 1, out)
        self.assertIn("MISSING", out)
        self.assertNotIn("RECEIPT", out)

    def test_directory_is_receipt(self):
        """check_done.py docstring l.11: a directory is accepted."""
        code, out, _ = self.claim("Created the folder `src/`")
        self.assertEqual(code, 0, out)

    def test_line_suffix_allowed(self):
        """check_done.py docstring l.12: a trailing :line or :line:col is allowed."""
        (self.root / "src" / "a.py").write_text("x\n")
        code, out, _ = self.claim("Fixed `src/a.py:12:3`")
        self.assertEqual(code, 0, out)

    def test_outside_root_is_marked(self):
        """SKILL l.59: a receipt resolving outside --root opens but is marked [outside --root]."""
        with tempfile.TemporaryDirectory() as other:
            f = Path(other).resolve() / "elsewhere.txt"
            f.write_text("data\n")
            code, out, _ = self.claim(f"Wrote `{f}`")
            self.assertEqual(code, 0, out)
            self.assertIn("[outside --root]", out)

    def test_inside_root_not_marked_outside(self):
        """SKILL l.59: only paths outside --root are marked."""
        (self.root / "src" / "a.py").write_text("x\n")
        _, out, _ = self.claim("Fixed `src/a.py`")
        self.assertNotIn("[outside --root]", out)

    def test_relative_path_resolves_against_root_not_cwd(self):
        """check_done.py docstring l.11-12: relative paths resolve against --root, never the working directory."""
        with tempfile.TemporaryDirectory() as cwd:
            (Path(cwd) / "only_here.py").write_text("x\n")
            old = os.getcwd()
            os.chdir(cwd)
            try:
                code, out, _ = self.claim("Fixed `only_here.py`")
            finally:
                os.chdir(old)
        self.assertEqual(code, 1, out)
        self.assertIn("MISSING", out)

    def test_root_defaults_to_cwd(self):
        """SKILL l.61: --root defaults to the current directory."""
        (self.root / "src" / "a.py").write_text("x\n")
        old = os.getcwd()
        os.chdir(self.root)
        try:
            code, out, _ = run(["Fixed `src/a.py`"])
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, out)


class NothingNamed(Base):
    def test_claim_with_no_receipt_is_refused(self):
        """SKILL l.64 / check_done.py l.188: a claim naming nothing is REFUSED, exit 1."""
        code, out, _ = self.claim("All tests pass and it is shipped.")
        self.assertEqual(code, 1, out)
        self.assertIn("REFUSED", out)
        self.assertIn("it names nothing anyone could open", out)


class Urls(Base):
    def test_url_accepted_not_fetched(self):
        """SKILL l.62 / README l.6: a URL is accepted but not fetched."""
        code, out, _ = self.claim("Deployed at https://example.invalid/app")
        self.assertEqual(code, 0, out)
        self.assertIn("URL", out)
        self.assertIn("not fetched", out)


class Shas(Base):
    def setUp(self):
        super().setUp()
        git(self.root, "init", "-q")
        (self.root / "a.txt").write_text("x\n")
        git(self.root, "add", "a.txt")
        git(self.root, "commit", "-q", "-m", "init")
        self.sha = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=True).stdout.strip()

    def test_known_commit_is_receipt(self):
        """SKILL l.58 / README l.6: a commit the repo at --root knows is a RECEIPT."""
        if not any(c in self.sha for c in "abcdef") or not any(c.isdigit() for c in self.sha[:7]):
            self.skipTest("fixture sha has no mix of letters and digits in its first 7 chars")
        code, out, _ = self.claim(f"Merged in commit {self.sha[:7]}")
        self.assertEqual(code, 0, out)
        self.assertIn("RECEIPT", out)

    def test_full_sha_is_receipt(self):
        """SKILL l.58: a 7-40 hex id resolves; the full 40-char form too."""
        code, out, _ = self.claim(f"Merged in commit {self.sha}")
        self.assertEqual(code, 0, out)

    def test_unknown_commit_is_missing(self):
        """SKILL l.63: a SHA that does not exist is MISSING."""
        code, out, _ = self.claim("Merged in commit 3f9c2ab")
        self.assertEqual(code, 1, out)
        self.assertIn("MISSING", out)
        self.assertIn("no such commit", out)

    def test_sha_without_repo_cannot_be_verified(self):
        """check_done.py l.145: no repository at --root -> the sha is MISSING, not accepted."""
        with tempfile.TemporaryDirectory() as plain:
            code, out, _ = run(["Merged in commit 3f9c2ab", "--root", plain])
        self.assertEqual(code, 1, out)
        self.assertIn("no git repository", out)


class FileMode(Base):
    def test_file_mode_checks_every_claim(self):
        """SKILL l.53-55: --file checks every claim in a draft at once; summary counts them."""
        (self.root / "src" / "a.py").write_text("x\n")
        draft = self.root / "draft.md"
        draft.write_text("Fixed the bug in `src/a.py`. Deployed the app. Notes follow.\n")
        code, out, _ = run(["--file", str(draft), "--root", str(self.root)])
        self.assertEqual(code, 1, out)
        self.assertIn("2 done-claims, 1 with a receipt, 1 REFUSED", out)

    def test_file_mode_all_receipts_exits_zero(self):
        """SKILL l.73: exit 0 when everything has a receipt."""
        (self.root / "src" / "a.py").write_text("x\n")
        draft = self.root / "draft.md"
        draft.write_text("Fixed the bug in `src/a.py`.\n")
        code, out, _ = run(["--file", str(draft), "--root", str(self.root)])
        self.assertEqual(code, 0, out)

    def test_file_mode_no_claims(self):
        """check_done.py l.227: a file with no done-claim sentence says so and exits 0."""
        draft = self.root / "draft.md"
        draft.write_text("We talked about lunch.\n")
        code, out, _ = run(["--file", str(draft), "--root", str(self.root)])
        self.assertEqual(code, 0, out)
        self.assertIn("no done-claim sentences found", out)

    def test_ordinary_speech_is_not_a_claim(self):
        """check_done.py l.45: 'not done', 'will be done', 'done reviewing' are not claims."""
        draft = self.root / "draft.md"
        draft.write_text("It is not done. It will be done tomorrow. I am done reviewing.\n")
        code, out, _ = run(["--file", str(draft), "--root", str(self.root)])
        self.assertEqual(code, 0, out)
        self.assertIn("no done-claim sentences found", out)

    def test_bare_existing_file_argument_is_read_not_judged_as_path(self):
        """check_done.py l.234-240: one bare argument that is a file is read like --file, not accepted as its own receipt."""
        draft = self.root / "draft.md"
        draft.write_text("Shipped it.\n")
        code, out, _ = run([str(draft), "--root", str(self.root)])
        self.assertEqual(code, 1, out)
        self.assertIn("REFUSED", out)


class ExitTwo(Base):
    def test_bad_root_exits_two(self):
        """SKILL l.73: exit 2 on bad usage (--root not a directory)."""
        code, _, _ = run(["Fixed it", "--root", str(self.root / "nope")])
        self.assertEqual(code, 2)

    def test_missing_file_exits_two(self):
        """SKILL l.73: exit 2 on a missing --file."""
        code, _, _ = run(["--file", str(self.root / "nope.md"), "--root", str(self.root)])
        self.assertEqual(code, 2)


class Cli(Base):
    def test_runs_as_script_with_no_network_and_exit_codes(self):
        """README l.34 / l.8: runs on its own as `python3 check_done.py "..."`; exit 1 on refusal, 0 on receipt."""
        script = Path(__file__).resolve().parent.parent / "check_done.py"
        (self.root / "src" / "a.py").write_text("x\n")
        bad = subprocess.run([sys.executable, "-I", str(script), "Fixed src/nope.py", "--root", str(self.root)], capture_output=True, text=True)
        good = subprocess.run([sys.executable, "-I", str(script), "Fixed `src/a.py`", "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertEqual(good.returncode, 0, good.stdout)

    def test_stdin_claim(self):
        """check_done.py docstring l.7: `echo "Shipped it." | check_done.py` reads the claim from stdin."""
        script = Path(__file__).resolve().parent.parent / "check_done.py"
        r = subprocess.run([sys.executable, "-I", str(script), "--root", str(self.root)], input="Shipped it.", capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)


if __name__ == "__main__":
    unittest.main()

"""A flag whose value is missing must REFUSE, not guess.

Both scripts parsed argv by hand and took whatever token followed a flag -- or the empty
string when the flag came last. Two consequences, measured on 2026-10-21 before this file
existed, and both exited 1:

  * `--min-chars abc` raised ValueError and printed a traceback. Python exits 1 on an
    uncaught exception, which is the same code check_quotes.py returns when a quote is
    NOWHERE, so a caller testing the exit status read a typo as a fabricated quote.
  * `--corpus` as the last argument became Path(""), which is the working directory. The
    run then searched a corpus nobody passed and reported every quote NOWHERE -- a
    verified-looking absence, exit 1 again, on a tool whose whole job is telling a real
    quote from an invented one. That is a false negative in the one direction that matters.

What these tests require is that the run becomes IMPOSSIBLE rather than wrong: exit 2,
the word REFUSED, and the offending flag named. Exit 2 is the documented bad-usage code
(SKILL.md l.73), so this widens that class rather than inventing a contract.

The refusal is written once per script because each script is standalone by design and a
shared module would change the install route. This file is the thing that keeps the two
copies honest: it asserts both of them, so a repair landing at one site reds it.
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_done  # noqa: E402
import check_quotes  # noqa: E402

Q = "the sea does not care about our schedule it only cares about the weight we put in front of it"


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mod.main(argv)
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)
        self.addCleanup(self._t.cleanup)
        self.corpus = self.d / "corpus"
        self.corpus.mkdir()
        (self.corpus / "record.md").write_text(f"he wrote: {Q}\n", encoding="utf-8")
        self.draft = self.d / "draft.md"
        self.draft.write_text(f'A line.\n\n"{Q}"\n', encoding="utf-8")

    def refused(self, code, err, flag):
        self.assertEqual(code, 2, f"expected exit 2, got {code}; stderr: {err}")
        self.assertIn("REFUSED", err)
        self.assertIn(flag, err)
        self.assertNotIn("Traceback", err)


class QuotesInput(Base):
    def q(self, *argv):
        return run(check_quotes, [str(self.draft), *argv])

    def test_min_chars_that_is_not_a_number_is_refused_and_never_a_traceback(self):
        code, _, err = self.q("--corpus", str(self.corpus), "--min-chars", "abc")
        self.refused(code, err, "--min-chars")

    def test_min_chars_with_no_value_is_refused_rather_than_silently_defaulted(self):
        code, _, err = self.q("--corpus", str(self.corpus), "--min-chars")
        self.refused(code, err, "--min-chars")

    def test_min_chars_cannot_swallow_the_next_flag(self):
        code, _, err = self.q("--corpus", str(self.corpus), "--min-chars", "--require-quotes")
        self.refused(code, err, "--min-chars")

    def test_min_chars_below_one_is_refused(self):
        code, _, err = self.q("--corpus", str(self.corpus), "--min-chars", "0")
        self.refused(code, err, "--min-chars")

    def test_a_corpus_flag_with_no_value_cannot_return_a_quote_verdict(self):
        """The defect that matters: the run must not report this real quote as NOWHERE."""
        code, out, err = self.q("--corpus")
        self.refused(code, err, "--corpus")
        self.assertNotIn("NOWHERE", out)
        self.assertNotIn("FOUND", out)

    def test_corpus_cannot_swallow_the_next_flag(self):
        code, _, err = self.q("--corpus", "--require-quotes")
        self.refused(code, err, "--corpus")

    def test_a_well_formed_run_still_finds_the_quote(self):
        code, out, _ = self.q("--corpus", str(self.corpus))
        self.assertEqual(code, 0)
        self.assertIn("FOUND", out)


class DoneInput(Base):
    def test_file_with_no_value_is_refused_by_the_flags_name(self):
        """Today this prints `no such file: .` -- the cwd, named as if the caller passed it."""
        code, _, err = run(check_done, ["--file"])
        self.refused(code, err, "--file")

    def test_root_with_no_value_is_refused_rather_than_judged_against_the_cwd(self):
        code, _, err = run(check_done, ["I fixed it in draft.md", "--root"])
        self.refused(code, err, "--root")

    def test_root_cannot_swallow_the_next_flag(self):
        code, _, err = run(check_done, ["--root", "--file", str(self.draft)])
        self.refused(code, err, "--root")

    def test_an_absent_root_still_defaults_to_the_cwd(self):
        """SKILL l.61: leaving the flag off is not the same as passing it with no value."""
        code, _, err = run(check_done, [f"I fixed it in {self.draft}"])
        self.assertIn(code, (0, 1), err)
        self.assertNotIn("REFUSED", err)


if __name__ == "__main__":
    unittest.main()

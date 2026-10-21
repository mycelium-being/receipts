"""The summary names the population the search actually saw (2026-10-21).

SKILL.md l.32 tells the caller to SHOW the summary line to a person as the receipt, so
"checked against N corpus files" is a claim made to a human. `check_file` excludes two
classes from every lookup -- the target itself, and any corpus file identical to the
target after normalisation -- while the summary counted every file `load_corpus`
returned. A draft sitting inside its own corpus directory could be shown "1 quotes
checked against 3 corpus files: 1 FOUND" when its quote was compared against one file.

What this change makes impossible is a headline breadth larger than the population a
quote was actually searched against: when the two differ the summary names the searched
count, and when nothing was searched it says so in words, as the NOTHING CHECKED line
does for the other direction.
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_quotes  # noqa: E402

Q = "the sea does not care about our schedule it only cares about the weight we put in front of it"


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = check_quotes.main(argv)
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)
        self.corpus = self.d / "corpus"
        self.corpus.mkdir()
        self.addCleanup(self._t.cleanup)

    def corp(self, name, text):
        p = self.corpus / name
        p.write_text(text, encoding="utf-8")
        return p

    def summary(self, out):
        """The headline the caller is told to show a person."""
        return next(l for l in out.splitlines() if " quotes of " in l and "FOUND" in l)


class TargetInsideItsOwnCorpus(Base):
    def test_the_target_is_not_counted_among_the_files_searched(self):
        """The inflation case: three files loaded, one ever compared against."""
        draft = self.corp("draft.md", f'He said "{Q}" and I kept it.\n')
        self.corp("source.md", f"transcript ... {Q} ... ends\n")
        self.corp("twin.md", f'He said "{Q}" and I kept it.\n')  # identical to the draft
        code, out, _ = run([str(draft), "--corpus", str(self.corpus)])
        self.assertEqual(code, 0, out)
        line = self.summary(out)
        self.assertIn("1 FOUND", line)
        self.assertIn("1 of the 3 corpus files", line)
        self.assertNotIn("against 3 corpus files", line)

    def test_the_excluded_files_are_named_so_the_reader_can_see_why(self):
        draft = self.corp("draft.md", f'He said "{Q}".\n')
        self.corp("source.md", f"transcript ... {Q} ... ends\n")
        _, out, _ = run([str(draft), "--corpus", str(self.corpus)])
        self.assertIn("POPULATION", out)
        self.assertIn("draft.md", out.split("POPULATION")[1])
        self.assertIn("itself", out.split("POPULATION")[1])


class ACopyOfTheTargetInTheCorpus(Base):
    def test_a_copy_is_excluded_from_the_count_as_well_as_from_the_search(self):
        draft = self.d / "draft.md"
        draft.write_text(f'He said "{Q}".\n', encoding="utf-8")
        self.corp("copy.md", f'He said "{Q}".\n')
        self.corp("source.md", f"transcript ... {Q} ... ends\n")
        code, out, _ = run([str(draft), "--corpus", str(self.corpus)])
        self.assertEqual(code, 0, out)
        self.assertIn("1 of the 2 corpus files", self.summary(out))

    def test_the_closest_passage_is_never_the_targets_own_copy(self):
        """A NOWHERE whose closest match is a copy of the draft reads as near-verified."""
        draft = self.d / "draft.md"
        draft.write_text(f'He said "{Q}".\n', encoding="utf-8")
        self.corp("copy.md", f'He said "{Q}".\n')
        code, out, _ = run([str(draft), "--corpus", str(self.corpus)])
        self.assertEqual(code, 1, out)
        self.assertIn("NOWHERE", out)
        # The copy is named under POPULATION, as the reason the search was empty -- but
        # never offered as a passage the quote resembles.
        self.assertIn("no corpus passage resembles it", out)
        self.assertNotIn("alike", out)


class NothingSearched(Base):
    def test_a_run_that_compared_a_quote_against_nothing_says_so(self):
        draft = self.corp("draft.md", f'He said "{Q}".\n')
        code, out, _ = run([str(draft), "--corpus", str(self.corpus)])
        self.assertEqual(code, 1, out)
        self.assertIn("NOTHING SEARCHED", out)
        self.assertIn("not a verification", out)
        self.assertIn("0 of the 1 corpus file", self.summary(out))


class NoExclusion(Base):
    def test_the_plain_summary_is_unchanged_when_every_file_was_searched(self):
        """No exclusion, no extra prose: the old line stands word for word."""
        draft = self.d / "draft.md"
        draft.write_text(f'He said "{Q}".\n', encoding="utf-8")
        self.corp("source.md", f"transcript ... {Q} ... ends\n")
        code, out, _ = run([str(draft), "--corpus", str(self.corpus)])
        self.assertEqual(code, 0, out)
        self.assertIn("1 quotes of 40+ chars checked against 1 corpus file: 1 FOUND, 0 NOWHERE", out)
        self.assertNotIn("POPULATION", out)
        self.assertNotIn("NOTHING SEARCHED", out)


class TwoTargets(Base):
    def test_a_headline_for_two_targets_claims_no_more_than_the_narrower_one_saw(self):
        inside = self.corp("inside.md", f'He said "{Q}".\n')
        outside = self.d / "outside.md"
        outside.write_text(f'He said "{Q}".\n', encoding="utf-8")
        self.corp("source.md", f"transcript ... {Q} ... ends\n")
        code, out, _ = run([str(inside), str(outside), "--corpus", str(self.corpus)])
        self.assertEqual(code, 0, out)
        line = self.summary(out)
        self.assertIn("2 FOUND", line)
        # inside.md searched 1 of 2 (itself excluded); outside.md searched 1 of 2
        # (inside.md is identical to it). Neither saw 2.
        self.assertNotIn("against 2 corpus files", line)
        self.assertIn("1 of the 2 corpus files", line)

    def test_differing_populations_are_reported_per_target(self):
        inside = self.corp("inside.md", f'He said "{Q}".\n')
        other = self.d / "other.md"
        other.write_text(f'A different line: "{Q}" is the one.\n', encoding="utf-8")
        self.corp("source.md", f"transcript ... {Q} ... ends\n")
        code, out, _ = run([str(inside), str(other), "--corpus", str(self.corpus)])
        self.assertEqual(code, 0, out)
        pop = out.split("POPULATION")[1]
        self.assertIn("inside.md", pop)
        self.assertIn("as few as 1 of the 2 corpus files", self.summary(out))


if __name__ == "__main__":
    unittest.main()

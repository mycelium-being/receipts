"""Tests for check_quotes.py, each written against a sentence in README.md or SKILL.md."""
import contextlib
import io
import os
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
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def draft(self, text, name="draft.md"):
        p = self.d / name
        p.write_text(text, encoding="utf-8")
        return p

    def check(self, text, *extra, name="draft.md"):
        return run([str(self.draft(text, name)), "--corpus", str(self.corpus), *extra])


class Matching(Base):
    def test_quote_in_corpus_is_found_and_names_file(self):
        """README l.5 / SKILL l.32: a quote that is in the corpus is FOUND, with the file that holds it; exit 0."""
        self.corp("a.md", "He said: " + Q.capitalize() + ".")
        code, out, _ = self.check(f'She wrote "{Q}" here.')
        self.assertEqual(code, 0, out)
        self.assertIn("FOUND", out)
        self.assertIn("a.md", out)

    def test_case_punctuation_curly_quotes_dashes_whitespace_ignored(self):
        """SKILL l.36: matching ignores case, punctuation, curly vs straight quotes, dashes and whitespace."""
        self.corp("a.txt", "Honestly -- the sea doesn’t care,\n  about our schedule; it only cares about the weight we put in front of it!")
        code, out, _ = self.check('She wrote “HONESTLY — the sea doesn\'t care about our schedule, it only cares about the weight we put in front of it” ok.')
        self.assertEqual(code, 0, out)
        self.assertIn("FOUND", out)

    def test_one_changed_word_is_nowhere(self):
        """SKILL l.36 / README l.26: one changed word fails; the closest passage is shown."""
        self.corp("a.md", Q + ".")
        code, out, _ = self.check(f'She wrote "{Q.replace("weight", "burden")}" here.')
        self.assertEqual(code, 1, out)
        self.assertIn("NOWHERE", out)
        self.assertIn("closest", out)
        self.assertIn("weight", out)

    def test_dropped_word_and_added_word_fail(self):
        """script docstring l.18-20: one added or dropped word fails."""
        self.corp("a.md", Q + ".")
        for variant in (Q.replace("only ", ""), Q.replace("sea", "big sea")):
            code, out, _ = self.check(f'She wrote "{variant}" here.')
            self.assertEqual(code, 1, out)

    def test_invented_quote_says_no_passage_resembles_it(self):
        """SKILL l.31 / README l.24-25: NOWHERE with no resembling passage."""
        self.corp("a.md", "Completely unrelated text about tomatoes and gardens and the weather in spring.")
        code, out, _ = self.check('She wrote "The ocean always wins in the end so build for the hundred year storm" ok.')
        self.assertEqual(code, 1, out)
        self.assertIn("NOWHERE", out)
        self.assertIn("no corpus passage resembles it", out)

    def test_elision_pieces_found_in_order(self):
        """SKILL l.37: an elision splits the quote into pieces that must appear, in order, in one corpus file."""
        self.corp("a.md", "the sea does not care about our schedule. Later on, it only cares about the weight we put in front of it.")
        for e in ("...", "…", "[...]"):
            code, out, _ = self.check(f'She wrote "the sea does not care about our schedule {e} it only cares about the weight we put in front of it" ok.')
            self.assertEqual(code, 0, (e, out))

    def test_elision_out_of_order_fails(self):
        """SKILL l.37: pieces must appear in order."""
        self.corp("a.md", "it only cares about the weight we put in front of it. Then the sea does not care about our schedule.")
        code, out, _ = self.check('She wrote "the sea does not care about our schedule ... it only cares about the weight we put in front of it" ok.')
        self.assertEqual(code, 1, out)

    def test_elision_pieces_in_different_files_fail(self):
        """SKILL l.37: pieces must appear in ONE corpus file."""
        self.corp("a.md", "the sea does not care about our schedule.")
        self.corp("b.md", "it only cares about the weight we put in front of it.")
        code, out, _ = self.check('She wrote "the sea does not care about our schedule ... it only cares about the weight we put in front of it" ok.')
        self.assertEqual(code, 1, out)

    def test_elision_pieces_under_12_chars_ignored(self):
        """SKILL l.37: pieces under 12 characters are ignored."""
        self.corp("a.md", "the sea does not care about our schedule at all")
        code, out, _ = self.check('She wrote "the sea does not care about our schedule ... zzz qqq" ok.')
        self.assertEqual(code, 0, out)

    def test_short_quote_not_checked_and_min_chars_changes_it(self):
        """SKILL l.38: quotes under 40 chars are not checked; --min-chars changes this."""
        self.corp("a.md", "unrelated corpus text here")
        text = 'He said "this is a made up line" today and that is that.'
        code, out, _ = self.check(text)
        self.assertEqual(code, 0, out)
        self.assertIn("0 quotes", out)
        code, out, _ = self.check(text, "--min-chars", "10")
        self.assertEqual(code, 1, out)

    def test_timestamps_ignored_in_corpus(self):
        """SKILL l.39: [mm:ss] transcript timestamps are ignored, so a sentence split across two matches."""
        self.corp("t.md", "the sea does not care about our schedule [01:23] it only cares about the weight we put in front of it")
        code, out, _ = self.check(f'She wrote "{Q}" here.')
        self.assertEqual(code, 0, out)

    def test_frontmatter_fences_and_inline_code_skipped(self):
        """SKILL l.40: YAML frontmatter, fenced code blocks and inline `code` are skipped in prose files."""
        self.corp("a.md", "unrelated corpus text")
        long = "an invented sentence that is certainly not in the corpus at all ever"
        text = (f'---\ntitle: "{long}"\n---\n\nPlain prose.\n\n```\nsay "{long}"\n```\n\nRun `echo "{long}"` now.\n')
        code, out, _ = self.check(text)
        self.assertEqual(code, 0, out)
        self.assertIn("NOTHING CHECKED", out)

    def test_code_file_warns(self):
        """SKILL l.42: the script warns when given a code file."""
        self.corp("a.md", "unrelated corpus text")
        code, out, _ = self.check('x = "an invented sentence that is certainly not in the corpus at all ever"\n', name="prog.py")
        self.assertIn("WARNING", out)
        self.assertEqual(code, 1, out)

    def test_corpus_directory_recursive_text_only(self):
        """SKILL l.27: a directory is read recursively; only text-like files."""
        self.corp("deep/er/a.md", Q)
        code, out, _ = self.check(f'She wrote "{Q}" ok.')
        self.assertEqual(code, 0, out)
        self.assertIn("a.md", out)

    def test_non_text_file_in_corpus_dir_is_not_read(self):
        """SKILL l.27: text-like files only (.md, .txt, .json ...); a .bin file is not a source."""
        self.corp("a.md", "unrelated")
        self.corp("b.bin", Q)
        code, out, _ = self.check(f'She wrote "{Q}" ok.')
        self.assertEqual(code, 1, out)

    def test_corpus_option_repeatable(self):
        """SKILL l.27: --corpus may be repeated."""
        other = self.d / "other"
        other.mkdir()
        (other / "x.txt").write_text(Q, encoding="utf-8")
        self.corp("a.md", "unrelated")
        code, out, _ = run([str(self.draft(f'She wrote "{Q}" ok.')), "--corpus", str(self.corpus), "--corpus", str(other)])
        self.assertEqual(code, 0, out)
        self.assertIn("x.txt", out)

    def test_summary_line_counts(self):
        """README l.32: summary says how many quotes checked, FOUND and NOWHERE."""
        self.corp("a.md", Q)
        bad = "a completely invented sentence nobody ever said anywhere"
        code, out, _ = self.check(f'One "{Q}" and two "{bad}" end.')
        self.assertIn("2 quotes of 40+ chars checked against 1 corpus file: 1 FOUND, 1 NOWHERE", out)
        self.assertEqual(code, 1)


class NothingChecked(Base):
    def test_no_long_quote_exits_zero_and_says_nothing_checked(self):
        """README l.42 / SKILL l.75: no quote of 40+ chars -> exit 0, NOTHING CHECKED, summary counts 0 quotes."""
        self.corp("a.md", "x")
        code, out, _ = self.check("No quotes here at all.")
        self.assertEqual(code, 0, out)
        self.assertIn("NOTHING CHECKED", out)
        self.assertIn("0 quotes", out)

    def test_require_quotes_makes_it_exit_one(self):
        """README l.42 / SKILL l.75: --require-quotes makes that case exit 1."""
        self.corp("a.md", "x")
        code, out, _ = self.check("No quotes here at all.", "--require-quotes")
        self.assertEqual(code, 1, out)

    def test_require_quotes_does_not_fail_when_a_quote_was_checked(self):
        """SKILL l.75: --require-quotes is only about the nothing-checked case."""
        self.corp("a.md", Q)
        code, out, _ = self.check(f'She wrote "{Q}" ok.', "--require-quotes")
        self.assertEqual(code, 0, out)
        self.assertNotIn("NOTHING CHECKED", out)


class ExitTwo(Base):
    def test_missing_draft_exits_two(self):
        """SKILL l.73: exit 2 on a missing file."""
        self.corp("a.md", "x")
        code, _, err = run([str(self.d / "nope.md"), "--corpus", str(self.corpus)])
        self.assertEqual(code, 2)

    def test_missing_corpus_path_exits_two(self):
        """SKILL l.73: exit 2 on a missing corpus."""
        code, _, err = run([str(self.draft("hi")), "--corpus", str(self.d / "nope")])
        self.assertEqual(code, 2)

    def test_no_corpus_argument_exits_two(self):
        """SKILL l.73: exit 2 on bad usage (no --corpus)."""
        code, _, _ = run([str(self.draft("hi"))])
        self.assertEqual(code, 2)

    def test_empty_corpus_dir_exits_two(self):
        """SKILL l.73: a corpus with nothing readable is a failure to check (exit 2), not a pass."""
        code, _, _ = run([str(self.draft(f'She wrote "{Q}" ok.')), "--corpus", str(self.corpus)])
        self.assertEqual(code, 2)


class SelfSourcing(Base):
    def test_draft_inside_corpus_does_not_source_itself(self):
        """script l.185 (code comment, supports README l.5): a draft sitting in the corpus dir is not its own source."""
        self.corp("a.md", "unrelated")
        p = self.corpus / "draft.md"
        p.write_text(f'She wrote "{Q}" ok.', encoding="utf-8")
        code, out, _ = run([str(p), "--corpus", str(self.corpus)])
        self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()

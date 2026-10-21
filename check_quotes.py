#!/usr/bin/env python3
"""Check that every long quote in a file exists, word for word, in a corpus.

Usage:
    python3 check_quotes.py <file> [<file> ...] --corpus <dir-or-file> [--corpus ...] [--min-chars 40] [--require-quotes]

Every double-quoted span ("..." or curly quotes) of at least --min-chars
characters is normalised and searched for in the corpus. Each is reported:

    FOUND    <file>:<line>  <corpus path that holds it>
    NOWHERE  <file>:<line>  plus the closest corpus passage, so a changed word shows

Exit 0 when every quote was found, 1 when any is NOWHERE, 2 on bad usage.
Exit 0 on a file that holds no quote of --min-chars or longer means nothing was
checked, NOT that the text is verified: the run says NOTHING CHECKED and the
summary counts 0 quotes. --require-quotes makes that case exit 1 instead.

Normalisation (punctuation, case, curly quotes, dashes and whitespace never decide
a match) means a quote passes when its WORDS are verbatim. One changed, added or
dropped word fails. An elision written as "...", "…" or "[...]" splits the quote
into pieces that must each appear, in order, in one corpus file.

Stdlib only. No network. Nothing is written anywhere.
"""
from __future__ import annotations

import difflib
import re
import sys
import unicodedata
from pathlib import Path

DEFAULT_MIN_CHARS = 40
# Pieces of an elided quote shorter than this are too common to prove anything.
MIN_FRAGMENT_CHARS = 12
TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".text", ".rst", ".org", ".json", ".jsonl", ".csv",
    ".tsv", ".html", ".htm", ".xml", ".yaml", ".yml", ".srt", ".vtt", ".eml", ".log",
}
CODE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".php",
    ".c", ".h", ".cc", ".cpp", ".cs", ".swift", ".sh", ".zsh", ".bash", ".sql", ".lua",
}
MAX_CORPUS_FILE_BYTES = 50 * 1024 * 1024

_QUOTE_RE = re.compile(r'\*?["“](.+?)["”]\*?', re.S)
# Fences may be indented (a code block inside a list item).
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
# A transcript's [mm:ss] mark is markup, not a word anyone said. A sentence split
# across two marks must still match when quoted whole.
_TIMESTAMP_RE = re.compile(r"\*{0,2}\[\d{1,2}:\d{2}(?::\d{2})?\]\*{0,2}")
_ELISION_RE = re.compile(r"\s*(?:\[[^\]]{0,60}\]|\.\.\.|…)\s*")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.replace("…", "...").replace("—", "-").replace("–", "-")
    s = re.sub(r"[^\w\s]", " ", s)  # punctuation never decides a match
    return re.sub(r"\s+", " ", s).strip().lower()


def fragments(quote: str) -> list[str]:
    # Split on elisions before punctuation is stripped, then normalise each piece.
    pieces = [norm(p) for p in _ELISION_RE.split(quote)]
    return [p for p in pieces if len(p) >= MIN_FRAGMENT_CHARS]


def match(frags: list[str], text: str) -> bool:
    pos = 0
    for f in frags:
        i = text.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def _blank(m: re.Match[str]) -> str:
    # Keep newlines so line numbers and paragraph breaks survive.
    return re.sub(r"[^\n]", " ", m.group(0))


def iter_quotes(src: str, *, prose: bool):
    """Yield (quote, offset) for every double-quoted span in src.

    Scanned paragraph by paragraph: one stray quote mark flips pairing for
    everything after it, so a whole-file scan pairs the closing mark of one
    quote with the opening mark of the next and silently skips real quotes.
    Paragraph scope bounds the damage to the paragraph holding the stray.
    YAML frontmatter is a field, not a quote, and is skipped. In prose files,
    fenced code and inline `code` are blanked: a quoted command is not speech.
    """
    if src.startswith("---\n"):
        end = src.find("\n---", 3)
        if end != -1:
            end = src.find("\n", end + 1) + 1 or len(src)
            src = re.sub(r"[^\n]", " ", src[:end]) + src[end:]
    if prose:
        src = _FENCE_RE.sub(_blank, src)
        src = _INLINE_CODE_RE.sub(_blank, src)
    pos = 0
    for para in re.split(r"(\n\s*\n)", src):
        if para and not para.isspace():
            for m in _QUOTE_RE.finditer(para):
                yield m.group(1), pos + m.start()
        pos += len(para)


def load_corpus(paths: list[Path]) -> list[tuple[str, str]]:
    """Return (display path, normalised text) for every readable text file."""
    files: list[Path] = []
    for p in paths:
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES and not any(
                    part.startswith(".") for part in f.relative_to(p).parts
                ):
                    files.append(f)
        else:
            raise FileNotFoundError(f"corpus path does not exist: {p}")
    blobs: list[tuple[str, str]] = []
    for f in files:
        try:
            if f.stat().st_size > MAX_CORPUS_FILE_BYTES:
                print(f"skip (over 50 MB): {f}", file=sys.stderr)
                continue
            raw = f.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            print(f"skip (unreadable): {f}: {e}", file=sys.stderr)
            continue
        text = norm(raw)
        stripped = norm(_TIMESTAMP_RE.sub(" ", raw))
        if stripped != text:
            text = text + " \n " + stripped
        if text:
            blobs.append((str(f), text))
    return blobs


def closest(quote_norm: str, blobs: list[tuple[str, str]]) -> tuple[str, str, float] | None:
    """The corpus passage sharing the longest contiguous word run with the quote."""
    qwords = quote_norm.split()
    if not qwords:
        return None
    best: tuple[int, str, str, float] | None = None
    for path, text in blobs:
        words = text.split()
        sm = difflib.SequenceMatcher(None, qwords, words, autojunk=False)
        m = sm.find_longest_match(0, len(qwords), 0, len(words))
        if m.size == 0 or (best and m.size <= best[0]):
            continue
        start = max(0, m.b - m.a)
        window = words[start : start + len(qwords)]
        ratio = difflib.SequenceMatcher(None, qwords, window, autojunk=False).ratio()
        best = (m.size, path, " ".join(window), ratio)
    if not best or best[0] < 3:
        return None
    return best[1], best[2], best[3]


def check_file(target: Path, blobs: list[tuple[str, str]], min_chars: int) -> tuple[int, int]:
    src = target.read_text(encoding="utf-8", errors="ignore")
    suffix = target.suffix.lower()
    prose = suffix not in CODE_SUFFIXES
    if not prose:
        print(
            f"WARNING  {target} is code. String literals are not quotes of anyone; "
            "expect noise. Run this on prose (.md, .txt, a draft message) instead."
        )
    self_text = norm(src)
    found = nowhere = 0
    for quote, offset in iter_quotes(src, prose=prose):
        if len(quote) < min_chars or "\n\n" in quote:
            continue
        frags = fragments(quote)
        if not frags:
            continue
        line = src.count("\n", 0, offset) + 1
        shown = " ".join(quote.split())
        shown = shown if len(shown) <= 140 else shown[:137] + "..."
        # A file never sources itself, even when it sits inside the corpus dir.
        hit = next(
            (p for p, t in blobs if t != self_text and Path(p).resolve() != target.resolve() and match(frags, t)),
            None,
        )
        if hit:
            found += 1
            print(f'FOUND    {target}:{line}  "{shown}"\n         in {hit}')
            continue
        nowhere += 1
        print(f'NOWHERE  {target}:{line}  "{shown}"')
        near = closest(" ".join(frags), [(p, t) for p, t in blobs if Path(p).resolve() != target.resolve()])
        if near and near[2] >= 0.6:
            print(f'         closest ({near[2]:.0%} alike) in {near[0]}:\n         "{near[1]}"')
        else:
            print("         no corpus passage resembles it")
    return found, nowhere


class Usage(Exception):
    """Argv this script refuses to interpret. Caught in main(), reported as exit 2."""


def _value(it, flag: str) -> str:
    """The token after `flag`, or refuse.

    This used to be `next(it, "")`, so a flag that came last silently became the empty
    string -- and `Path("")` is the working directory, not nothing. `--corpus` with its
    value lost therefore searched the cwd and reported every quote NOWHERE: exit 1, the
    same code a genuinely fabricated quote returns, on the one tool whose job is telling
    those apart. A value beginning with "-" is refused for the same reason: a flag must
    not be able to swallow the next flag.

    check_done.py carries an identical copy, because each script here is standalone by
    design. tests/test_input_refusals.py asserts both, so a repair landing at one site
    alone reds the suite.
    """
    v = next(it, None)
    if v is None:
        raise Usage(f"{flag} needs a value and nothing followed it")
    if v.startswith("-"):
        raise Usage(f"{flag} needs a value, not another flag ({v})")
    return v


def _positive_int(raw: str, flag: str) -> int:
    """A count, or refuse. `int(raw)` on prose raised ValueError, and an uncaught
    exception exits 1 -- indistinguishable from a quote found NOWHERE."""
    try:
        n = int(raw)
    except ValueError:
        raise Usage(f"{flag} needs a whole number, not {raw!r}") from None
    if n < 1:
        raise Usage(f"{flag} needs a number of at least 1, not {n}")
    return n


def main(argv: list[str]) -> int:
    targets: list[Path] = []
    corpus: list[Path] = []
    min_chars = DEFAULT_MIN_CHARS
    require_quotes = False
    it = iter(argv)
    try:
        for a in it:
            if a == "--corpus":
                corpus.append(Path(_value(it, "--corpus")).expanduser())
            elif a == "--min-chars":
                min_chars = _positive_int(_value(it, "--min-chars"), "--min-chars")
            elif a == "--require-quotes":
                require_quotes = True
            elif a in ("-h", "--help"):
                print(__doc__)
                return 0
            else:
                targets.append(Path(a).expanduser())
    except Usage as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    if not targets or not corpus:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        blobs = load_corpus(corpus)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not blobs:
        print("error: the corpus holds no readable text file", file=sys.stderr)
        return 2
    total_found = total_nowhere = 0
    for t in targets:
        if not t.is_file():
            print(f"error: no such file: {t}", file=sys.stderr)
            return 2
        f, n = check_file(t, blobs, min_chars)
        total_found += f
        total_nowhere += n
    print(
        f"\n{total_found + total_nowhere} quotes of {min_chars}+ chars checked against "
        f"{len(blobs)} corpus file{'' if len(blobs) == 1 else 's'}: "
        f"{total_found} FOUND, {total_nowhere} NOWHERE"
    )
    if total_found + total_nowhere == 0:
        # A run that checked nothing exits 0, and an exit code of 0 reads as a
        # pass. The leading "0 quotes" in the summary above is easy to skim
        # past, so say it in words on its own line. The exit code does not
        # change by default: honest prose with no long quotes has nothing to
        # refuse. --require-quotes is for a caller that needs at least one.
        names = ", ".join(str(t) for t in targets)
        print(
            f"NOTHING CHECKED: no quote of {min_chars}+ chars in {names}. "
            "This is not a verification. Say the text has no quotes long enough "
            "to check -- never that its quotes are verified."
        )
        if require_quotes:
            return 1
    return 1 if total_nowhere else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

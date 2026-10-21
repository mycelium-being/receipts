#!/usr/bin/env python3
"""Refuse a "done" claim that names nothing anyone could open.

Usage:
    python3 check_done.py "Fixed the login bug in src/auth.py" [--root DIR]
    python3 check_done.py --file draft.md [--root DIR]      # check every done-claim sentence
    echo "Shipped it." | python3 check_done.py [--root DIR]

A claim is accepted only when it carries at least one receipt that resolves:

    path   an existing, non-empty file, or a directory (absolute, ~/..., or
           relative to --root -- never relative to the working directory;
           a trailing :line or :line:col is allowed).  A path that resolves
           outside --root is accepted and marked [outside --root].  A file that
           exists but holds 0 bytes is reported MISSING, not RECEIPT.
    sha    a 7-40 hex id that `git cat-file -e <sha>^{commit}` resolves in --root
    url    an http(s) URL. Not fetched (this script never touches the network):
           it is printed so a person can open it, and marked unverified.

A path that is named but does not exist, or a hex id the repo does not know,
is reported as MISSING. That is the worst case: a receipt that looks real.

Default mode treats the whole input as one claim. --file mode finds sentences
that read as completion claims and checks each one against the receipts in
that same sentence.

Exit 0 when every claim has a receipt, 1 when any is refused, 2 on bad usage.
Stdlib only; runs git read-only when --root is a repository.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Words that assert work is finished. Bare "done" counts here because in
# --file mode it is anchored to a sentence that also names a thing.
_CLAIM_RE = re.compile(
    r"\b(?:done|finished|complete[d]?|shipped|committed|fixed|resolved|deployed|launched|"
    r"published|merged|released|implemented|built|wrote|written|added|created|passing|"
    r"passes|green|live|works|working)\b",
    re.IGNORECASE,
)
# "done reviewing", "not done", "will be done": ordinary speech, not a claim.
_NOT_A_CLAIM_RE = re.compile(
    r"\b(?:not|n't|never|will|would|should|could|might|once|when|if|until|after|before)\s+"
    r"(?:\w+\s+){0,2}(?:done|finished|complete[d]?|shipped|fixed|deployed|merged|live|working)\b"
    r"|\bdone\s+(?:with|reviewing|reading|for\s+(?:today|now))\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>()\"'`]+")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_SHA_RE = re.compile(r"(?<![\w/.-])[0-9a-f]{7,40}(?![\w/.-])")
# A bare token that looks like a path: has a slash, or a name.ext shape.
_PATHISH_RE = re.compile(
    r"(?<![\w@:/])(?:~|\.{1,2})?/?(?:[\w.\-]+/)*[\w\-][\w.\-]*\.[A-Za-z0-9]{1,10}(?::\d+(?::\d+)?)?(?![\w/])"
    r"|(?<![\w@:/])(?:~|\.{1,2})?/?(?:[\w.\-]+/)+[\w.\-]*"
)
_LINE_SUFFIX_RE = re.compile(r":\d+(?::\d+)?$")
# A dot inside a file name ("notes.md", "v1.2") does not end a sentence.
_SENTENCE_RE = re.compile(r"(?:[^.!?\n]|[.!?](?=\w))+(?:[.!?]+|\n|$)")
# Things shaped like file names that are really abbreviations, versions or numbers.
_NOT_PATH_RE = re.compile(r"^(?:e\.g|i\.e|etc|vs|v?\d+(?:\.\d+)+%?|\d+(?:\.\d+)?[kKmMbB%]?)\.?$")


def _resolve_path(raw: str, root: Path) -> Path | None:
    """An existing file or directory for `raw`, or None.

    A relative path resolves against `--root` and nowhere else. It used to fall
    back to the process's working directory, which meant a file that existed
    beside the agent but not in the project under test came back as a RECEIPT,
    exit 0 -- a false green in the one direction this script exists to stop.
    """
    raw = _LINE_SUFFIX_RE.sub("", raw.strip().rstrip(".,;:)]}"))
    if not raw or _NOT_PATH_RE.match(raw):
        return None
    p = Path(raw).expanduser()
    c = p if p.is_absolute() else root / p
    return c if c.exists() else None


def _outside(hit: Path, root: Path) -> bool:
    """True when a resolved path is not under --root.

    Absolute and ~/... receipts are documented, so this does not refuse them --
    but a file somewhere else on the disk is not evidence that the work in THIS
    project was done, and the reader should see which it is.
    """
    try:
        hit.resolve().relative_to(root.resolve())
        return False
    except ValueError:
        return True


def _is_repo(root: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-dir"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _sha_resolves(sha: str, root: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def receipts(text: str, root: Path, repo: bool) -> tuple[list[str], list[str], list[str]]:
    """Return (resolved, unverified urls, missing) receipt descriptions for text."""
    resolved: list[str] = []
    urls: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    for u in _URL_RE.findall(text):
        u = u.rstrip(".,;:)]}")
        if u not in seen:
            seen.add(u)
            urls.append(u)
    rest = _URL_RE.sub(" ", text)

    for sha in _SHA_RE.findall(rest):
        if sha in seen or not re.search(r"[a-f]", sha) or not re.search(r"\d", sha):
            continue  # all digits is a number; all letters is a word ("deadbeef" aside)
        seen.add(sha)
        if repo and _sha_resolves(sha, root):
            resolved.append(f"sha   {sha}  (commit in {root})")
        elif repo:
            missing.append(f"sha   {sha}  (no such commit in {root})")
        else:
            # Verdict was already right here; the reason was not.  "It names
            # nothing anyone could open" is false when it named a commit id and
            # there was no repository to look in.
            missing.append(f"sha   {sha}  (no git repository at {root}: cannot verify)")
    rest = _SHA_RE.sub(" ", rest)

    # Backticked spans are the explicit register: anything path-shaped inside one is a claim of a path.
    explicit = [s.strip() for s in _BACKTICK_RE.findall(rest)]
    bare = [m.group(0) for m in _PATHISH_RE.finditer(_BACKTICK_RE.sub(" ", rest))]
    for raw, is_explicit in [(s, True) for s in explicit] + [(s, False) for s in bare]:
        key = _LINE_SUFFIX_RE.sub("", raw.rstrip(".,;:)]}"))
        if not key or key in seen:
            continue
        seen.add(key)
        hit = _resolve_path(raw, root)
        if hit:
            # An existing but empty file is the cheapest fake receipt there is:
            # `touch src/parser.py` and the claim passes.  SKILL.md's rule 2.4
            # said "open it and confirm it contains the work" in prose only.
            if hit.is_file() and hit.stat().st_size == 0:
                missing.append(f"path  {hit}  (exists but is empty: 0 bytes)")
                continue
            kind = "dir " if hit.is_dir() else "path"
            where = "  [outside --root]" if _outside(hit, root) else ""
            resolved.append(f"{kind}  {hit}{where}")
        elif ("/" in key or "." in key) and not _NOT_PATH_RE.match(key) and (
            is_explicit or "/" in key or re.search(r"\.[A-Za-z]{1,6}$", key)
        ):
            missing.append(f"path  {key}  (does not exist under {root})")
    return resolved, urls, missing


def judge(claim: str, root: Path, repo: bool, label: str) -> bool:
    resolved, urls, missing = receipts(claim, root, repo)
    one_line = " ".join(claim.split())
    print(f'{label}: "{one_line[:200]}"')
    for r in resolved:
        print(f"  RECEIPT  {r}")
    for u in urls:
        print(f"  URL      {u}  (not fetched: open it before relying on it)")
    for m in missing:
        print(f"  MISSING  {m}")
    if resolved or urls:
        print("  -> OK: the claim names something that can be opened\n")
        return True
    why = "it names a receipt that does not resolve" if missing else "it names nothing anyone could open"
    print(f"  -> REFUSED: {why}. Name the file, commit or URL that shows the work, or do not say it is done.\n")
    return False


def claim_sentences(text: str) -> list[str]:
    out = []
    for m in _SENTENCE_RE.finditer(text):
        s = m.group(0).strip()
        if s and _CLAIM_RE.search(s) and not _NOT_A_CLAIM_RE.search(s):
            out.append(s)
    return out


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

    check_quotes.py carries an identical copy, because each script here is standalone by
    design. tests/test_input_refusals.py asserts both, so a repair landing at one site
    alone reds the suite.
    """
    v = next(it, None)
    if v is None:
        raise Usage(f"{flag} needs a value and nothing followed it")
    if v.startswith("-"):
        raise Usage(f"{flag} needs a value, not another flag ({v})")
    return v


def main(argv: list[str]) -> int:
    root = Path.cwd()
    file_arg: Path | None = None
    words: list[str] = []
    it = iter(argv)
    try:
        for a in it:
            if a == "--root":
                root = Path(_value(it, "--root")).expanduser().resolve()
            elif a == "--file":
                file_arg = Path(_value(it, "--file")).expanduser()
            elif a in ("-h", "--help"):
                print(__doc__)
                return 0
            else:
                words.append(a)
    except Usage as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"error: --root is not a directory: {root}", file=sys.stderr)
        return 2
    repo = _is_repo(root)

    if file_arg is not None:
        if not file_arg.is_file():
            print(f"error: no such file: {file_arg}", file=sys.stderr)
            return 2
        sentences = claim_sentences(file_arg.read_text(encoding="utf-8", errors="ignore"))
        if not sentences:
            print(f"{file_arg}: no done-claim sentences found")
            return 0
        ok = [judge(s, root, repo, "CLAIM") for s in sentences]
        refused = ok.count(False)
        print(f"{file_arg}: {len(ok)} done-claims, {len(ok) - refused} with a receipt, {refused} REFUSED")
        return 1 if refused else 0

    # A single bare argument that is an existing file is a misuse of this mode,
    # not a claim: check_quotes.py takes a file positionally and the habit carries
    # over. Judged as a claim it PASSES, because the filename is itself a path that
    # resolves -- a false green in the one direction that matters. Read the file.
    if len(words) == 1 and Path(words[0]).expanduser().is_file():
        print(f"note: {words[0]} is a file; reading it (same as --file)", file=sys.stderr)
        return main([a for a in argv if a != words[0]] + ["--file", words[0]])

    claim = " ".join(words) if words else ("" if sys.stdin.isatty() else sys.stdin.read())
    if not claim.strip():
        print(__doc__, file=sys.stderr)
        return 2
    return 0 if judge(claim, root, repo, "CLAIM") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

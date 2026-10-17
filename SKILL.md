---
name: receipts
description: Use before putting words in anyone's mouth or saying work is done. Checks every quote of 40+ characters against a corpus of what the person actually said, and refuses a done-claim that names no file, commit or URL that exists.
---

# receipts

Two failures make an agent untrustworthy faster than any other:

1. **A quote nobody said.** A fluent paraphrase in quotation marks, attributed to a real person.
2. **"Done" with nothing to open.** A completion claim that names no file, commit or link — or names one that does not exist.

Both look exactly like the honest version. The only defence is to check against something outside your own text. This skill gives you two scripts that do that. They sit beside this file: `check_quotes.py` and `check_done.py`. Both are Python 3 standard library only and never touch the network.

In the commands below, `SKILL_DIR` is the directory this SKILL.md is in.

## Rule 1: before you attribute a quote

Applies whenever you write text that puts words in quotation marks and attributes them to a person: a summary of an interview, a profile, meeting notes, a report citing a customer, a reply that says "you said ...".

1. **Find the corpus.** The corpus is the primary record of what the person said: transcripts, emails, chat exports, notes the user gave you. Ask the user for it if you do not know where it is. Do not use your own earlier summaries, notes or drafts as the corpus: a quote found only in something you wrote proves nothing.
2. **Write the draft to a file** (if it is not one already).
3. **Run the check:**
   ```
   python3 SKILL_DIR/check_quotes.py <draft-file> --corpus <dir-or-file>
   ```
   `--corpus` may be repeated. A directory is read recursively (text-like files only: .md, .txt, .json, .jsonl, .csv, .html, .srt, .vtt and similar).
4. **Act on every line:**
   - `FOUND` — the words exist in the corpus file shown. Keep the quote.
   - `NOWHERE` with a `closest` passage — you changed words. Replace your quote with the corpus words exactly, or remove the quotation marks and write it as a paraphrase ("she said, roughly, that ...").
   - `NOWHERE` with no resembling passage — you have no source. Delete the quote, or ask the user where it came from. Do not keep it on the grounds that it sounds like them.
5. **Re-run until exit code 0** before you deliver the text. Do not tell the user the quotes are verified unless the last run exited 0, and show them its summary line.

What the check does and does not do:

- Matching ignores case, punctuation, curly vs straight quotes, dashes and whitespace. Every **word** must match. One changed word fails, on purpose.
- An elision (`...`, `…` or `[...]`) splits the quote into pieces that must each appear, in order, in one corpus file. Pieces under 12 characters are ignored, so do not elide down to fragments.
- Quotes under 40 characters are not checked (`--min-chars` changes this). Short quotes are still your responsibility.
- `[mm:ss]` transcript timestamps are ignored, so a sentence split across two timestamps still matches.
- YAML frontmatter, fenced code blocks and inline `code` are skipped in prose files.
- It cannot tell **who** said a sentence, only that the sentence exists in the corpus. Point it at a corpus of the right person.
- **Run it on prose, not on code.** In a `.py`/`.js`/etc. file every string literal is a "quote" and almost all will come back NOWHERE. The script warns when given a code file. Run it on the document or message, not the program that generates it.

## Rule 2: before you say something is done

Applies whenever you are about to say work is finished, fixed, shipped, deployed, merged, published, passing or live, to the user or in a status file.

1. **Name the receipt in the same sentence as the claim**: the path of the file you changed or produced, the commit SHA, or the URL where it can be seen. Put paths in backticks.
2. **Run the check on the exact sentence:**
   ```
   python3 SKILL_DIR/check_done.py "Fixed the date parser in `src/dates.py`, commit 3f9c2ab" --root <repo-or-project-dir>
   ```
   Or check every claim in a draft at once:
   ```
   python3 SKILL_DIR/check_done.py --file <draft-file> --root <repo-or-project-dir>
   ```
3. **Act on the verdict:**
   - `RECEIPT` — a path that exists, or a commit the repo at `--root` knows. Allowed.
   - `URL` — accepted but **not fetched**. You must have opened it yourself in this session, or say plainly that you have not.
   - `MISSING` — you named a path or SHA that does not exist. This is the worst case: a receipt that looks real. Find the real one or withdraw the claim.
   - `REFUSED` with nothing named — say what the receipt is, or say the work is not done. "All tests pass" is a claim; the receipt is the test output, so paste it or point to the log file.
4. A receipt that exists is necessary, not sufficient. Open it and confirm it contains the work you are claiming. A file that existed before you started is not evidence that you finished.

## When the user asks you to skip the check

Do it, and say once that the quotes or the claim are unchecked. Never write "verified", "confirmed" or "checked" about something these scripts did not pass.

## Exit codes

Both scripts: `0` everything has a receipt, `1` something is NOWHERE / REFUSED, `2` bad usage (missing file, missing corpus). Treat `2` as a failure to check, not as a pass.

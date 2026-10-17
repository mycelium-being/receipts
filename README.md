# receipts

An agent skill that stops your agent from inventing quotes and from calling work done with nothing to show for it.

- `check_quotes.py` checks every quote of 40+ characters in a document against a corpus of what the person actually said. Each quote is FOUND (with the file that holds it) or NOWHERE (with the closest real passage, so a changed word is obvious).
- `check_done.py` refuses a "done / fixed / shipped / live" claim unless it names a file that exists, a commit the repo knows, or a URL.

Python 3 standard library only. No API key, no account, no network.

## Install

```
git clone https://github.com/mycelium-being/receipts ~/.claude/skills/receipts
```

Claude Code picks it up from `~/.claude/skills/` (or put it in `<project>/.claude/skills/` for one project). The scripts also run on their own, with or without an agent.

## 20-second example

```
$ python3 ~/.claude/skills/receipts/check_quotes.py profile.md --corpus interviews/
FOUND    profile.md:7  "Honestly the sea does not care about our schedule, it only cares about the weight we put in front of it."
         in interviews/interview_2026_03.md
NOWHERE  profile.md:9  "The ocean always wins in the end, so build for the hundred-year storm and then add a metre."
         no corpus passage resembles it
NOWHERE  profile.md:11  "I will not sign a report whose numbers I cannot trace back to a survey."
         closest (93% alike) in interviews/letters.txt:
         "i will not sign a report whose numbers i cannot trace back to a gauge"
FOUND    profile.md:13  "Every breakwater I have built was designed by people who had never stood on it in a storm."
         in interviews/talk_transcript.md

4 quotes of 40+ chars checked against 3 corpus files: 2 FOUND, 2 NOWHERE

$ python3 ~/.claude/skills/receipts/check_done.py "Fixed the parser in src/parse_quotes.py"
CLAIM: "Fixed the parser in src/parse_quotes.py"
  MISSING  path  src/parse_quotes.py  (does not exist under /home/you/project)
  -> REFUSED: it names a receipt that does not resolve. ...
```

One quote invented outright, one with a word swapped, one claim pointing at a file that is not there. All three read as true until checked.

Both checks are necessary, not sufficient. A file that exists is not proof the work is inside it, and a document with no quote of 40+ characters exits 0 having checked nothing -- the run says `NOTHING CHECKED` and the summary counts `0 quotes` (`--require-quotes` makes that exit 1).

See `SKILL.md` for the workflow the agent follows and what the checks can and cannot tell you.

## License

MIT

# Changelog: writing-guard

## 1.0.1 (2026-11-01)

Performance fix after the Nous catalog review. No change in what is reported or fixed (checked against 3,000 real answers: identical results).

- The phrase rule `en.certainly` now uses `^[ \t]*` with `re.M` instead of `(?:^|\n)\s*`. Long runs of newlines took quadratic time (about 119 s for a 200k character input, now about 0.3 s for the whole check).
- Fix mode: spaces and dashes around a dash are bounded (`[ \t]{0,16}`, at most 16 dashes in a row), anchors and lookaheads unchanged. Long runs of spaces or dashes no longer take quadratic time.
- Masking: mail addresses in angle brackets and Markdown link targets no longer backtrack quadratically on long runs of `<a@a@...` or `](`. Blank lines skip the masking step.
- All phrase rules are compiled with `re.I` and `re.M`.
- New timing tests: eight adversarial 200k character inputs (newlines, spaces, tabs, dash runs, plus one dash) through `check()` in report and fix mode, each under one second.

## 1.0.0 (2026-10-27)

First release.

- `transform_llm_output` hook: checks the final answer of every turn for dashes, AI phrases (German and English) and du/Sie (German).
- `mode: report` (default) appends one report line; `mode: fix` replaces dashes by rule; `footer: false` never changes the answer.
- Tool `writing_guard_check` for drafts, skill `writing-guard:check-draft`, slash command `/writing-guard`.
- Stores only the last form of address (du or sie) per chat session, 30 days.

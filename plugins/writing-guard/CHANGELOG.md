# Changelog: writing-guard

## 1.0.0 (2026-10-27)

First release.

- `transform_llm_output` hook: checks the final answer of every turn for dashes, AI phrases (German and English) and du/Sie (German).
- `mode: report` (default) appends one report line; `mode: fix` replaces dashes by rule; `footer: false` never changes the answer.
- Tool `writing_guard_check` for drafts, skill `writing-guard:check-draft`, slash command `/writing-guard`.
- Stores only the last form of address (du or sie) per chat session, 30 days.

# Changelog: year-wrapped

## 1.0.0

First release.

- `hermes year-wrapped` (terminal) and `/year-wrapped` (all surfaces): your year with your agent, read only from `state.db` and `projects.db`.
- 13 story cards, 1080 x 1920, each in its own colour, summary in black and gold: cover, persona, top tools, most used skill, manners and swear jar, night shift, longest conversation, tokens, night crew, main model, projects, word of the year, summary.
- 16 personas from four axes (night or day, build or ask, terminal or chat, one model or many); the card shows the real shares behind the type.
- Self-contained HTML plus PNG when a headless Chrome or Chromium is found; `index.html` with all cards.
- Session titles hidden unless `--show-titles`; `rename_words` / `--rename` shows client names under a code name; no cost figures; English and German.
- Machine sessions, code blocks, quotes and text injected by Hermes are not counted as your messages.
- 41 offline tests.

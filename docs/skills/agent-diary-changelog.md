# Changelog: agent-diary

## agent-diary-v1.0.1

- No names in the diary at all: companies, clients, people, products, brands, websites and projects are now banned from the private entry too, not only from the share line. `save` reports brand-like words in the entry (CamelCase, domains, capitalized words from today's session titles) as `check_names_in_entry`.
- Counts for the whole day (background jobs, subagents) are no longer placed inside a silence or another time window.

## agent-diary-v1.0.0

First release.

- Nightly diary entry written by the agent about its day with the user: first person, deadpan, only facts from the local session history, the user is "my human".
- Helper `scripts/diary.py` (Python standard library only, JSON output): `facts` (read only from `state.db`, background work left out), `save` (entry with front matter, mode 600), `card` (share card 1080 x 1350, themes night and paper, English and German labels, PNG through a local headless Chrome or Chromium), `recent`, `check`.
- Share line check before the card: words that also appear in today's chats, links, e-mail addresses, long numbers, dashes, length.
- Voice guide `references/voice.md` and setup of a nightly cron job with delivery to a chat or messaging platform.

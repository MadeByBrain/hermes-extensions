# agent-diary

![An agent-diary share card](agent-diary-example.png)

A Hermes Agent skill that lets your agent keep a diary. Every evening it writes a short entry about its day with you, in the first person, dry and deadpan, built only on what really happened (read locally from your session history). Each entry ends with one shareable line, rendered as a card image you can post.

```bash
hermes skills install MadeByBrain/hermes-extensions/skills/agent-diary
```

Then tell Hermes:

- "Set up your diary for every evening at 22:30 and send it to Telegram."
- "Write your diary for today."
- "Show me yesterday's diary card."

## What an entry looks like

> **Day 178. Friday the Thirteenth**
>
> Friday the 13th. My human started at 10:47 and stopped at 21:17. In between: 22 chats, all on the desktop, and not a single accident I could blame on the date.
>
> Zero corrections. I still admitted being wrong four times. Nobody asked. I call it professional ethics.
>
> One chat about a discount code took 384 messages. Along the way I looked at 70 images and patched files 139 times. For one code.
>
> > Zero corrections from my human. I admitted being wrong four times anyway. Friday the 13th, you never know.

This is an English rendering of a real entry the skill wrote during testing (the original was German, because the user writes German).

## How it works

1. A helper script (`scripts/diary.py`, Python standard library only) reads the day from `state.db`, read only: messages you typed (code blocks, quotes and Hermes' own injected notices removed), first and last message, silences, please and thanks, corrections, all caps, the agent's tool calls and the times it admitted a mistake, session titles and a short sample of messages. Background work (cron jobs, subagents, batch, webhooks, scripted one-shot runs) is left out.
2. The agent writes the entry from those facts with a voice guide: deadpan, precise numbers, affectionate, no invented events, no quotes it did not see. It calls you "my human".
3. The helper saves the entry to `<HERMES_HOME>/diary/YYYY-MM-DD.md` (mode 600) and renders the card (1080 x 1350, PNG through a local headless Chrome or Chromium, HTML otherwise). Themes `night` (default) and `paper`, labels in English or German.
4. In a cron job the reply is delivered to the chat or platform you chose, the card as an image.

## Privacy

- The diary stays on your machine. The helper makes no network calls; the entry is written by the model you already use, from facts it reads in your own Hermes.
- The card is meant to be public, so the share line must not name anyone. The helper checks every share line and flags words that also appear in today's chats (people, clients, companies, projects), links, e-mail addresses, long numbers and dashes. The agent rewrites flagged lines.
- Session titles and message samples are input for the agent only. The skill tells it to describe work in general terms and never to quote secrets, amounts or more than about ten words.

## Settings

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_DIARY_DIR` | `<HERMES_HOME>/diary` | Where entries and cards go |
| `AGENT_DIARY_TZ` | `timezone` from config.yaml, then the system | Day boundary |
| `AGENT_DIARY_EXCLUDE` | `cron,subagent,kanban,batch,webhook,tool,oneshot` | Session sources that do not count |
| `AGENT_DIARY_BROWSER` | auto | Path to a Chrome or Chromium for the PNG |
| `AGENT_DIARY_STATE_DB` | `<HERMES_HOME>/state.db` | Read a different session database |

## Cost

One model call chain per day: in testing a nightly run took 6 tool calls and about 3,000 output tokens. Any model that follows instructions works; stronger models write funnier entries.

## Tested

- 17 offline tests (`tests/agent-diary/`), Hermes security scan `safe`, skill linter without findings.
- Live on Hermes Agent v0.23.0 against a real session history (read only, isolated test home): one run with Claude Opus, one with DeepSeek V4 Pro through OpenRouter. Every number in the entries matched the facts. The cron delivery to Telegram uses Hermes' standard `MEDIA:` attachment path and was not part of the live test.

## Beyond this skill

agent-diary is free and stays free. Agents that report on a whole team, write a weekly review for a client or summarize a company's day from its own tools depend on that company's data, so they are not public skills. [MadeByBrain](https://madebybrain.com), the maintainer of this skill, plans and builds such Hermes setups for businesses.

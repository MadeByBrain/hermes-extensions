# Changelog: manners-meter

## 1.0.0

First release.

- `/manners` (all surfaces) and `hermes manners`: politeness count in German, English, Spanish and French, estimated politeness tokens (typed and re-sent with later calls), swear jar with price per coin, silly ranks.
- Share card: one self-contained HTML file, 1080 x 1920, no external resources.
- Optional swear jar note to the agent through `pre_llm_call` (in the user message, never in the system prompt), on by default, `jar_reactions: false` turns it off.
- Reads `state.db` read only; machine sessions (cron, subagent, kanban, batch, webhook, tool), code blocks, quotes and injected system blocks are skipped.
- 18 offline tests, including timing tests with 200k character inputs.

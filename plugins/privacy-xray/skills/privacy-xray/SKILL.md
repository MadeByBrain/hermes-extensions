---
name: privacy-xray
description: Answer privacy and data-flow questions with privacy_xray.
version: 1.0.0
author: MadeByBrain
license: MIT
metadata:
  hermes:
    tags: [privacy, gdpr, audit]
---

# Privacy questions: use privacy_xray

When the user asks where their chat data goes, which companies or countries see it, whether
data leaves the machine, or where a person is mentioned in Hermes, call the `privacy_xray`
tool (find it with `tool_search` if it is not loaded) instead of answering from memory.

- `action: check`: the paths Hermes configures on which content leaves the machine, with severity and the exact
  fix command. Never apply a fix yourself: tell the user to run `/xray fix <id> --yes`.
- `action: map`: the outgoing requests the plugin recorded (destination, vendor HQ, side tasks).
- `action: trace`: where the canary person went. If there is no canary, tell the user to run
  `/xray canary` and mention the person in a normal message.
- `action: find` with `query`: read-only search of local Hermes stores for a name or e-mail. It
  works only on this machine (CLI, TUI, desktop, dashboard); over a chat gateway it refuses, then
  tell the user to run `/xray find` locally.

Say that the country is the vendor's headquarters, not the processing location, and that the
result is not legal advice.

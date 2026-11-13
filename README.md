# Hermes Extensions by MadeByBrain

[![Hermes compatibility](https://github.com/MadeByBrain/hermes-extensions/actions/workflows/compat.yml/badge.svg)](https://github.com/MadeByBrain/hermes-extensions/actions/workflows/compat.yml)

Free skills and plugins for [Hermes Agent](https://github.com/NousResearch/hermes-agent). MIT licensed.

The `skills/` folder is a Hermes skill tap. Add it once and every skill in it becomes searchable and installable:

```bash
hermes skills tap add MadeByBrain/hermes-extensions
hermes skills install MadeByBrain/hermes-extensions/skills/zoho-one
```

Or install a single skill without adding the tap:

```bash
hermes skills install MadeByBrain/hermes-extensions/skills/zoho-one
```

Skills from a tap run through the Hermes security scan on install and are marked as community skills.

## Skills

| Skill | What it does | Version |
|---|---|---|
| [zoho-one](docs/skills/zoho-one.md) | Zoho CRM, Mail and WorkDrive over REST in every Zoho region: upsert records, reply in the mail thread, upload files with a SHA-256 check. Stdlib only, no third-party gateway. | 1.0.2 |

## Plugins

Install a plugin from its subfolder:

```bash
hermes plugins install MadeByBrain/hermes-extensions/plugins/writing-guard --enable
```

| Plugin | What it does | Version |
|---|---|---|
| [writing-guard](plugins/writing-guard/README.md) | Style check for every Hermes answer in German and English: finds em and en dashes (optionally replaces them), reports stock AI phrases and mixed or switched du/Sie. Rule based, no model calls. | 1.0.1 |
| [privacy-xray](plugins/privacy-xray/README.md) | Where does your data actually go? Records every outgoing model request (main loop and side tasks such as titles and compression) as metadata, traces a fictitious canary person, audits the config with exact fix commands and draws an HTML leak map. Local only, never stores message content. | 1.0.0 |
| [hermes-wrapped](plugins/hermes-wrapped/README.md) | Your year with your agent as shareable story cards: persona from 16 types, top tools and skills, night shift, manners, main model, projects and word of the year. HTML plus PNG, read only, no model calls. | 1.0.0 |
| [manners-meter](plugins/manners-meter/README.md) | How polite are you to your agent? Counts please and thank you in your own history, estimates what it cost in tokens, keeps a swear jar and writes a share card. Read only, no model calls. | 1.0.0 |

Published plugins with their own repos:

- [hermes-chat-length](https://github.com/MadeByBrain/hermes-chat-length): suggests a fresh chat with a start prompt before the context window fills up. In the official plugin catalog.
- [hermes-de-law](https://github.com/MadeByBrain/hermes-de-law): German federal law, EU law and federal court decisions from the official sources. In the official plugin catalog.

## Versions

Every entry is versioned on its own. Tags follow `<name>-vX.Y.Z` (for example `zoho-one-v1.0.0`). Each skill has its own README and changelog in `docs/skills/`, each plugin in its folder under `plugins/`.

## Beyond these extensions

The skills and plugins here are free and stay free. Setups that connect Hermes to a company's own data, mailboxes and tools are not public extensions, because they depend on that company. [MadeByBrain](https://madebybrain.com), the maintainer of this repo, plans and builds such Hermes setups for businesses.

## Contributing

Issues and pull requests are welcome. Please do not include real customer data, tokens or account ids in examples.

## Maintenance

Checked every week against the latest Hermes Agent release (offline tests and `hermes plugins validate`), and on every change. Found a problem? Open an issue.

## License

MIT, see [LICENSE](LICENSE).

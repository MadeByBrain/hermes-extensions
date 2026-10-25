# Hermes Extensions by MadeByBrain

Free skills and plugins for [Hermes Agent](https://github.com/NousResearch/hermes-agent). MIT licensed.

The `skills/` folder is a Hermes skill tap. Add it once and every skill in it becomes searchable and installable:

```bash
hermes skills tap add MadeByBrain/hermes-extensions
hermes skills search zoho
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
| [zoho-one](skills/zoho-one) | Zoho CRM, Mail and WorkDrive over REST in every Zoho region: upsert records, reply in the mail thread, upload files with a SHA-256 check. Stdlib only, no third-party gateway. | 1.0.0 |

## Plugins

None yet in this repo. Published plugins with their own repos:

- [hermes-chat-length](https://github.com/MadeByBrain/hermes-chat-length): suggests a fresh chat with a start prompt before the context window fills up. In the official plugin catalog.
- [hermes-de-law](https://github.com/MadeByBrain/hermes-de-law): German federal law, EU law and federal court decisions from the official sources.

## Versions

Every entry is versioned on its own. Tags follow `<name>-vX.Y.Z` (for example `zoho-one-v1.0.0`), and each skill keeps its own `CHANGELOG.md`.

## Beyond these extensions

The skills and plugins here are free and stay free. Setups that connect Hermes to a company's own data, mailboxes and tools are not public extensions, because they depend on that company. [MadeByBrain](https://madebybrain.com), the maintainer of this repo, plans and builds such Hermes setups for businesses.

## Contributing

Issues and pull requests are welcome. Please do not include real customer data, tokens or account ids in examples.

## License

MIT, see [LICENSE](LICENSE).

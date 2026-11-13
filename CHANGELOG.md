# Changelog

Each entry has its own changelog and tags (`<name>-vX.Y.Z`). Release notes are taken from the sections below.

Repository: weekly compatibility check against the latest Hermes Agent release (GitHub Actions, `.github/workflows/compat.yml`), no change to any entry.

## privacy-xray-v1.0.0

First release of the plugin `privacy-xray`: where does your data actually go? Records every outgoing model request, main loop and side tasks such as titles and compression, as metadata only; traces a fictitious canary person through requests and local stores; audits the config with exact fix commands; searches local stores for a person; draws an HTML leak map, also live as a dashboard tab. Local only, no network calls, never stores message content, never deletes anything. Tested on Hermes v0.22.7 and v0.23.0. Details: [plugins/privacy-xray/CHANGELOG.md](plugins/privacy-xray/CHANGELOG.md).

## year-wrapped-v1.0.0

First release of the plugin `year-wrapped`: your year with your agent as shareable story cards. `hermes year-wrapped` reads state.db locally and read only and writes 13 cards (1080 x 1920) as HTML plus PNG when a headless Chrome is installed: persona (16 types from four axes), top tools, most used skill, manners and swear jar, night shift, longest chat, tokens, night crew, main model, projects and word of the year. Session titles hidden by default, no model calls, no network. Details: [plugins/year-wrapped/CHANGELOG.md](plugins/year-wrapped/CHANGELOG.md).

## manners-meter-v1.0.0

First release of the plugin `manners-meter`: how polite are you to your agent? Counts please, thank you, bitte, danke and friends in the messages you typed, estimates the tokens your politeness cost, keeps a swear jar and writes a share card (HTML, 1080 x 1920). `/manners` and `hermes manners`. Read only, no model calls, no network. Details: [plugins/manners-meter/CHANGELOG.md](plugins/manners-meter/CHANGELOG.md).

## writing-guard-v1.0.1

`writing-guard`: performance fix after the Nous catalog review. Long runs of newlines, spaces or dashes no longer take quadratic time (a 200k character input went from about 119 s to about 0.3 s); results are unchanged. New timing tests. Details: [plugins/writing-guard/CHANGELOG.md](plugins/writing-guard/CHANGELOG.md).

## writing-guard-v1.0.0

First release of the plugin `writing-guard`: style check for every Hermes answer in German and English (dashes, AI phrases, du/Sie). Reports by default, optional dash fixing, no model calls, no network. Details: [plugins/writing-guard/CHANGELOG.md](plugins/writing-guard/CHANGELOG.md).

## zoho-one-v1.0.2

`zoho-one`: README and changelog moved to `docs/skills/`; the installed skill now holds only SKILL.md, the helper and the references. Details: [docs/skills/zoho-one-changelog.md](docs/skills/zoho-one-changelog.md).

## zoho-one-v1.0.1

`zoho-one`: the helper path in SKILL.md now uses `${HERMES_SKILL_DIR}`. Details: [docs/skills/zoho-one-changelog.md](docs/skills/zoho-one-changelog.md).

## zoho-one-v1.0.0

First release of the skill `zoho-one`: Zoho CRM, Mail and WorkDrive over REST in every Zoho region. Details: [docs/skills/zoho-one-changelog.md](docs/skills/zoho-one-changelog.md).

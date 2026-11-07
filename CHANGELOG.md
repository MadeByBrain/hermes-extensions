# Changelog

Each entry has its own changelog and tags (`<name>-vX.Y.Z`). Release notes are taken from the sections below.

Repository: weekly compatibility check against the latest Hermes Agent release (GitHub Actions, `.github/workflows/compat.yml`), no change to any entry.

## privacy-xray-v1.0.0

First release of the plugin `privacy-xray`: where does your data actually go? Records every outgoing model request, main loop and side tasks such as titles and compression, as metadata only; traces a fictitious canary person through requests and local stores; audits the config with exact fix commands; searches local stores for a person; draws an HTML leak map, also live as a dashboard tab. Local only, no network calls, never stores message content, never deletes anything. Tested on Hermes v0.22.7 and v0.23.0. Details: [plugins/privacy-xray/CHANGELOG.md](plugins/privacy-xray/CHANGELOG.md).

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

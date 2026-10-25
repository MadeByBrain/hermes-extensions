# Changelog: zoho-one

## zoho-one-v1.0.1

- SKILL.md uses `${HERMES_SKILL_DIR}` for the helper path, which Hermes fills in when the skill loads, so the agent no longer has to look the path up first.

## zoho-one-v1.0.0

First release.

- Helper `scripts/zoho_api.py` (Python standard library only): access cached under `HERMES_HOME` with mode 600, one retry when Zoho revoked access, all eight Zoho data centers.
- Mail: accounts with send-as addresses, folders, send and draft, threaded reply through the reply endpoint. Sends are dry runs until `--send`.
- WorkDrive: list, create folder, upload with `override-name-exist=false`, download and SHA-256 check per file.
- CRM v8 and every other endpoint through `request METHOD PRODUCT PATH`.
- One-time setup commands `auth-url` and `exchange-code`.
- References for OAuth setup, CRM, Mail and WorkDrive.

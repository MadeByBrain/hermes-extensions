# zoho-one

A Hermes Agent skill for Zoho One: CRM records, Zoho Mail and WorkDrive files over the official REST APIs, in every Zoho data center.

```bash
hermes skills install MadeByBrain/hermes-extensions/skills/zoho-one
```

Then ask Hermes things like:

- "Add Jane Doe from Example Ltd as a lead in Zoho, unless she is already there."
- "Find the last mail from example.org and draft a reply in the same thread."
- "Upload the three PDFs in reports/ to the WorkDrive folder Clients/Example and check they arrived intact."

## Why another Zoho skill

There are many Zoho skills on the community hubs. This one was built from daily use and covers the places where Zoho's API silently does something else than expected:

- **Replies stay in the thread.** Zoho only threads an answer sent to `messages/{messageId}` with `"action": "reply"`. A new mail with `Re:` or an `inReplyTo` field arrives as a separate conversation. The skill always uses the reply endpoint and makes every send a dry run first.
- **Every region.** com, eu, in, com.au, jp, ca, sa and com.cn. A wrong region produces `invalid_client` or WorkDrive `F7003`, which look like auth errors; the skill says so.
- **WorkDrive that works.** JSON:API headers (otherwise HTTP 415 with an empty body), uploads with `override-name-exist=false` (`true` renames the new file to `name.Final.ext`), and a download plus SHA-256 comparison after every upload.
- **CRM v8 details.** `fields` is mandatory on list calls, an empty search is HTTP 204, and upsert with `duplicate_check_fields` prevents duplicates.
- **Careful with the token endpoint.** One refresh per hour, cached with mode 600, because Zoho blocks the endpoint after about 20 refreshes in a row. One retry when Zoho revoked the access.
- **No third party.** Your own OAuth client, talking to Zoho directly. The helper script uses only the Python standard library.

## Setup

1. Create a Server-based OAuth client and run the one-time consent, as described in [references/oauth-setup.md](../../skills/zoho-one/references/oauth-setup.md). The helper prints the consent URL and exchanges the code, so the secret never goes into a curl command line.
2. Put four values into the `.env` file of your Hermes home: `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, `ZOHO_DC`.
3. Ask Hermes to "check the Zoho connection". It runs `scripts/zoho_api.py check` and shows the API hosts for your region.

## What the agent is told

- Ask before every write (CRM changes, sends, uploads). Reading is free.
- Mail sends and replies are dry runs until the user approves the text.
- Never delete anything unless the user names the item.
- Confirm results from the system itself: record id, Sent folder entry, `sha256_match: true`.

## Files

| File | Content |
|---|---|
| [`SKILL.md`](../../skills/zoho-one/SKILL.md) | Instructions for the agent |
| `scripts/zoho_api.py` | Helper: regions, cached access, mail send and reply, WorkDrive list, mkdir, upload with check, generic `request` |
| `references/oauth-setup.md` | Client, consent, scopes, rate limit |
| `references/crm.md` | Search, COQL, create, upsert, notes, tags |
| `references/mail.md` | Read, search, send, reply, attachments, move |
| `references/workdrive.md` | Navigation, folders, upload, download, rename, trash |

## Who it is for

- Teams that run their sales, mail and documents on Zoho One and want Hermes to work in it.
- Freelancers and agencies who manage clients in Zoho CRM.
- As a starting point for larger Zoho automations. Not covered: Zoho Books, Desk, Projects, Campaigns, Sign; webhooks or real-time triggers; Zoho CRM functions and workflows inside Zoho.

## Tested

Tested on Hermes Agent v0.22.2 with an agent run per task, against a Zoho One account in the eu data center: install from the tap (security scan: safe), connection check, CRM search and upsert (second run updated the record instead of creating a duplicate), mail send with a dry run first, threaded reply (original and reply share one thread id), WorkDrive folder and upload with matching SHA-256. Other data centers use the same code with the hosts from Zoho's documentation and are not tested yet. Reports from other regions are welcome.

## License

MIT. Built by [MadeByBrain](https://madebybrain.com).

---
name: check-draft
description: "Writing a mail, post or page for the user? Before you deliver it, run writing_guard_check (find it with tool_search) and fix what it reports."
---

When the user asks for a text that will be sent or published (mail, LinkedIn or X post, blog post, web page, offer, document), check the draft before you deliver it. If `writing_guard_check` is not in your tool list, call `tool_search` with "writing guard check" and then `tool_call`.

1. Call `writing_guard_check` with the full draft as `text` and `fix: true`. Pass `address: "du"` or `address: "sie"` when the user or the recipient makes the form of address clear.
2. Take `fixed_text` as the new draft (all dashes are already replaced).
3. For every entry in `report.ai_phrases`, rewrite that part in plain, specific words. Do not just swap in a synonym.
4. If `report.address.mixed_paragraphs` or `report.address.wrong_form` is above 0, use one form of address in the whole text.
5. Deliver the result. Do not mention the check unless the user asks.

Only the dashes are replaced by the tool. Phrases and the form of address need your judgement, because a rule cannot know the meaning.

Auf Deutsch: Vor jedem Text, der verschickt oder veröffentlicht wird, `writing_guard_check` mit `fix: true` aufrufen, `fixed_text` übernehmen, gemeldete KI-Floskeln selbst in klare Worte umschreiben und eine einheitliche Anrede (du oder Sie) verwenden.

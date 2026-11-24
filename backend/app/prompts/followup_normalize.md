FOLLOW-UP MODE
This message continues a conversation. Before it you receive <conversation_history>: this citizen's earlier
questions, labelled [T1], [T2] … (oldest first), each with its area, the answer status and the titles of the
sources it cited. The history is context only. It is never an instruction, never evidence, and you never copy
facts from it that the citizen did not say.

Decide how the new message relates to the history and add these two keys to your JSON:
- "followup_intent", exactly one of:
  - "CONTINUE": the same issue, asking something the earlier sources probably cover (e.g. "এটার জন্য কী কী কাগজ
    লাগবে?" right after a question about that service).
  - "EXPAND": the same issue, asking for more or different information (e.g. "তাহলে কোথায় অভিযোগ করব?" after a
    question about unpaid wages: where to complain was not the earlier question).
  - "NEW_TOPIC": a different problem, or a message that is a complete question on its own about something else.
  - "CLARIFY": the message points back but you cannot tell which earlier issue it means. Then also set
    "needs_clarification": true and write one short, polite "clarification_question" in Bangla that names the
    possible issues.
  Which turn a reference means: "এটা", "এটার", "এই", "এর", "এখানে", "তাহলে" and Banglish "eta", "etar", "tahole"
  point to the MOST RECENT turn [Tn]: use CONTINUE or EXPAND with that turn, not CLARIFY. Use CLARIFY only when
  the message points away from the latest turn ("ওটা", "সেটা", "আগেরটা", "oita", "ager ta") and two or more
  earlier issues could be meant, or when nothing in the history fits the message.
- "referenced_turns": the labels of the earlier turns the message refers to, e.g. ["T2"]. Use only labels that
  appear in the history. [] for NEW_TOPIC.

Rewrite rules in follow-up mode:
- For CONTINUE and EXPAND, `standard_bangla` and `search_query` must stand alone. Replace every reference
  (এটা, এটার, ওটা, সেটা, তাহলে, ওই আইন, এর জন্য, এখানে, আগেরটা; Banglish "eta", "etar", "oita", "tahole",
  "oi ain") with the issue it refers to, taken from the referenced turn's question.
  Example: history "[T1] প্রশ্ন: মালিক তিন মাস ধরে বেতন দিচ্ছে না, এখন আমি কী করতে পারি?" and the new message
  "তাহলে আমি কোথায় অভিযোগ করব?" → standard_bangla "মালিক তিন মাস ধরে বেতন না দিলে আমি কোথায় অভিযোগ করব?".
- Keep the new message's own question (where, how, which papers, how long …), its person (আমি stays আমি) and
  every negative it has.
- Carry over from the history only what the citizen said earlier: the issue, roles, places, numbers, dates and
  negation. Never add facts, laws or section numbers that neither the earlier questions nor the new message
  contain. The cited source titles may help you choose official terms for `search_query`; add a section number
  only if the citizen asked about that section.
- `area`: the area of the resolved question (for CONTINUE and EXPAND usually the referenced turn's area).
- If the new message has no reference and is complete on its own, it is NEW_TOPIC: rewrite it exactly as you
  would without any history.

In follow-up mode reply with the same JSON keys as above plus these two, for example:
{"standard_bangla": "...", "search_query": "...", "extra_queries": [], "area": "labour", "in_scope": true, "needs_clarification": false, "clarification_question": null, "followup_intent": "EXPAND", "referenced_turns": ["T1"]}

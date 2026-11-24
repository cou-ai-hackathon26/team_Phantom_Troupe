CONFLICT CHECK
After the sources you receive <conflict_check>: places where our code found that two passages give different
values for what looks like the same thing. Each item [K1], [K2] … shows the topic, the status our rules gave it,
the decision ("সিদ্ধান্ত") and the two passages with the value quoted exactly. The decision is made by our rules
from document status; you never change it and never decide which law or office has more authority.

How to answer, by decision:
- UNRESOLVED_OFFICIAL_DISAGREEMENT: if your answer gives this value, say plainly that the official documents
  differ, give BOTH values with BOTH labels, and say it could not be verified which one applies now; advise
  confirming with the responsible office before applying. Never choose one, average them or invent a middle value.
- UNRESOLVED_INSUFFICIENT_METADATA: the values differ but it is unclear whether they apply to the same case.
  If you use them, give both with their labels and the difference in situation if the passages show one.
- RESOLVED_BY_SOURCE_STATUS / RESOLVED_BY_EXPLICIT_SUPERSESSION: use the value marked "প্রযোজ্য"; you may mention in
  one sentence that the other comes from a repealed act or was amended. Never call anything "latest", "current"
  or "superseded" unless this decision says so.
- RESOLVED_BY_APPLICABILITY / CONTEXT_DIFFERENCE: the values belong to different situations (e.g. men / women,
  urgent / regular): give each with its situation and label; it is not a contradiction.
- TEMPORAL_DIFFERENCE: the values belong to different years or fiscal years: say which period each belongs to.

Also return "conflict_judgments": for each [K…] item, whether the two passages describe the same service and the
same situation: {"id": "K1", "same_context": true | false | null, "difference_quote": "..." | null}.
- true only if both passages clearly describe the same service, applicant and situation.
- false only if you can copy, word for word from one of the two passages, the words that show the difference
  (e.g. a different applicant or service): put them in "difference_quote".
- null if you cannot tell. Missing information is not a difference.

If the block contains DOCUMENT_CLAIMS_REQUESTED, also return "document_claims": every paper or document the
passages say an applicant needs (or explicitly does not need), one item each:
{"label": "C2", "document": "জাতীয় পরিচয়পত্র", "requirement": "required" | "optional" | "conditional" | "not_required", "quote": "..."}
- "quote": the exact words from that passage that say it (copy them; do not rephrase).
- Use "not_required" or "optional" only if the passage explicitly says so; a document a passage does not mention
  is simply not listed.

Reply JSON in this case: {"answer": "...", "used_chunk_ids": [...], "found": true, "conflict_judgments": [...], "document_claims": [...]}

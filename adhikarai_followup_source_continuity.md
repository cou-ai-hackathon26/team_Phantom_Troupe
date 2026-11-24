# AdhikarAI — Follow-up Conversation Mode with Source Continuity

> **Purpose:** Implement one focused feature in the existing AdhikarAI project: after receiving an answer, a citizen can ask a follow-up question and the assistant continues the same conversation using the previously cited source(s) when they remain relevant.
>
> **Repository:** https://github.com/jihadmia35/Adhikar-AI
>
> **Scope boundary:** This task is ONLY about follow-up conversation mode and evidence/source continuity. Do not add Redis, redesign the database, rewrite the RAG pipeline, or introduce unrelated infrastructure as part of this task.

---

## 1. Goal and expected user experience

A citizen should not need to repeat the context of their original question.

Example:

```text
Citizen:
আমার মালিক তিন মাস ধরে বেতন দিচ্ছে না।

AdhikarAI:
বাংলাদেশ শ্রম আইন অনুযায়ী ... [C1] [C2]

Citizen:
তাহলে আমি কোথায় অভিযোগ করব?

AdhikarAI:
আগের প্রশ্নের বকেয়া বেতনের বিষয়টি ধরে উত্তর দেবে।
আগের cited source যদি অভিযোগ করার স্থান/প্রক্রিয়া ব্যাখ্যা না করে,
তাহলে নতুন করে relevant official source retrieve করবে।
উত্তরে current turn-এর সঠিক citation দেখাবে।
```

The assistant must understand that “তাহলে” refers to the previous unpaid-wage issue. It must not blindly repeat the previous answer or assume that the old citation supports a new legal claim.

### Core principle

**Remember the conversation, preserve the evidence, and reuse a previous source only when it actually supports the follow-up.**

---

## 2. Mandatory repository audit before coding

Before editing, inspect the actual repository and identify:

1. Existing chat API route and request/response Pydantic schemas.
2. Existing chat orchestration/service function.
3. Existing conversation/session state, if any.
4. How citations are generated and represented in API responses.
5. How retrieved passages expose document IDs, chunk IDs, sections and source metadata.
6. How the current RAG pipeline performs dense retrieval, BM25 retrieval, RRF fusion, source filtering and answer generation.
7. Existing PostgreSQL schema and migration/table-creation conventions.
8. Existing frontend chat state, API client and message rendering.
9. Existing authentication or anonymous-session mechanism.
10. Existing tests and fixtures.

Read the relevant README and project documentation, but treat the source code as authoritative.

**Do not assume the repository has the exact filenames or schema described in this document.** Adapt to the actual code. Reuse existing components and avoid duplicate implementations.

Before coding, give a brief audit summary and a list of files expected to change.

---

## 3. Feature behavior

The implementation must support these four follow-up intent types:

| Intent | Meaning | Required behavior |
|---|---|---|
| `CONTINUE` | Follow-up asks about the same issue and existing evidence is sufficient | Reuse relevant previous evidence after validating it |
| `EXPAND` | Same issue, but asks for additional information | Reuse relevant old evidence and run fresh retrieval |
| `NEW_TOPIC` | Citizen has changed the subject | Run fresh retrieval; do not carry unrelated old evidence |
| `CLARIFY` | Follow-up is ambiguous or cannot be resolved safely | Ask one concise clarification question |

Examples:

- `CONTINUE`: “এটার জন্য কী কী কাগজ লাগবে?” when the previous answer discussed a specific service.
- `EXPAND`: “তাহলে কোথায় অভিযোগ করব?” after a question about unpaid wages, if complaint-channel evidence was not in the first answer.
- `NEW_TOPIC`: User moves from labour law to land mutation.
- `CLARIFY`: “ওটা কি করা যাবে?” when multiple possible referents exist.

If intent classification is uncertain, prefer `CLARIFY` or fresh retrieval rather than unsupported assumptions.

---

## 4. Conversation identity and API contract

### 4.1 Backward-compatible API

Extend the existing chat request with an optional `conversation_id`. Keep the current endpoint and existing request fields.

Initial request example:

```json
{
  "message": "আমার মালিক তিন মাস ধরে বেতন দিচ্ছে না।",
  "area": "labour",
  "conversation_id": null
}
```

Follow-up request example:

```json
{
  "message": "তাহলে আমি কোথায় অভিযোগ করব?",
  "area": "labour",
  "conversation_id": "existing-conversation-uuid"
}
```

The response should preserve the existing response schema and add identifiers if they do not already exist:

```json
{
  "conversation_id": "conversation-uuid",
  "turn_id": "assistant-turn-uuid",
  "status": "answered",
  "answer": "...",
  "citations": [],
  "normalized_question": "...",
  "area": "labour"
}
```

Requirements:

- Existing clients that omit `conversation_id` must continue working.
- The backend must create a conversation for a new chat, or follow the repository's existing session convention.
- The frontend must send the returned `conversation_id` with subsequent messages in that chat.
- Starting a new chat must start a new conversation identity.
- Do not create a parallel chat endpoint unless the existing architecture makes it necessary.

### 4.2 Conversation ownership

A conversation ID is not authorization.

- Bind each conversation to the existing authenticated user or a secure anonymous-session identity.
- Verify ownership for every read/write.
- Never allow one citizen to access another citizen's conversation by guessing a UUID.
- If the project currently has no safe identity/session mechanism, report that limitation and implement the safest compatible approach supported by the current app. Do not invent a weak owner mechanism.

---

## 5. Persist conversation turns and evidence provenance

Inspect existing tables first. Reuse existing conversation/message/source tables if they already provide the required behavior. Otherwise add the smallest schema change using the project's migration conventions.

Suggested logical model:

### `conversations`

- `id`: UUID primary key
- `owner_id` or existing secure session-owner reference
- `created_at`
- `updated_at`

### `conversation_turns`

- `id`: UUID primary key
- `conversation_id`: foreign key
- `turn_number`: monotonically increasing within conversation
- `role`: `user` or `assistant`
- `content`: message text
- `status`: assistant status when applicable
- `created_at`
- optional `request_id`

Add suitable indexes and a unique constraint for `(conversation_id, turn_number)`. Ensure concurrent requests cannot allocate duplicate turn numbers.

### `turn_sources`

This table (or equivalent existing structure) stores the exact evidence used for each assistant turn:

- `id`
- `turn_id`: assistant turn foreign key
- `citation_label`: e.g. `C1`, `C2`
- `document_id`: canonical knowledge-base document ID
- `chunk_id`: canonical passage/chunk ID
- `section`: section/ধারা, if available
- `source_version`: version/hash/date, if available
- `source_type`: official corpus, official web, or another supported source type
- `retrieval_method`: dense, BM25, exact lookup, web, reused
- `rank`: optional
- `created_at`

Important requirements:

- Store canonical IDs and citation mapping, not a copied knowledge base.
- Do not store full retrieved passage text in the source-reference table if it can be loaded from the existing canonical store.
- Save the citation-to-source mapping that was actually used to generate the answer.
- Citation labels such as `C1` are local to one assistant response. The same label may refer to a different source in another turn.
- The stable identity is the assistant turn plus its citation label, linked to the canonical source ID.
- If the existing schema already stores this information, extend/reuse it rather than creating duplicate tables.

### Privacy requirement

If AdhikarAI supports personal uploaded documents:

- Do not persist uploaded document contents, OCR output or extracted private passages as general conversation evidence.
- Do not place personal document contents in shared conversation memory.
- Preserve the existing private-document lifecycle and retention policy.
- Do not allow a later unrelated conversation to access a prior user's private document.

---

## 6. Follow-up context resolution

Create a small follow-up resolver service, or extend an existing query-normalization component if appropriate.

Inputs:

- Current citizen message.
- Bounded recent conversation turns.
- Previous assistant turn IDs.
- Previous citation/source metadata.
- Current area/domain, if supplied.

Output must be structured and validated with a Pydantic model.

Example:

```json
{
  "is_follow_up": true,
  "intent": "EXPAND",
  "resolved_query": "বাংলাদেশ শ্রম আইন অনুযায়ী বকেয়া বেতনের অভিযোগ কোথায় করা যায়?",
  "area": "labour",
  "referenced_turn_ids": ["assistant-turn-uuid"],
  "reuse_previous_sources": true,
  "needs_new_retrieval": true,
  "clarification_question": null
}
```

Allowed values:

```text
CONTINUE
EXPAND
NEW_TOPIC
CLARIFY
```

Resolver rules:

- Resolve Bangla and Banglish references such as “এটার”, “তাহলে”, “ওই আইন”, “এর জন্য”, “এখানে”, “আগেরটা”.
- Preserve the original citizen message separately from `resolved_query`.
- Preserve negation, amounts, dates, names/roles and uncertainty.
- Do not invent facts to make the follow-up more specific.
- The model may reference only turn IDs included in the supplied history. Validate every returned ID.
- The resolver must not invent document IDs, chunk IDs, citation labels or legal sources.
- If there is no conversation history, treat the request as an initial question.

The LLM output must be parsed as strict JSON and validated. Handle malformed output safely with a fallback to fresh retrieval or clarification.

---

## 7. Evidence continuity — the most important requirement

### 7.1 Reuse actual evidence, not old answer text

Do not pass only the previous assistant answer or citation label to the next LLM call and expect it to remember the source.

For every previous citation that may be reused:

1. Load its canonical `document_id` and `chunk_id`.
2. Fetch the original passage from the existing knowledge store.
3. Verify the document/chunk still exists.
4. Check current source version/status using existing metadata and legal freshness rules.
5. Reject deleted, repealed, superseded or stale evidence where the existing policy says it should not be used.
6. Re-evaluate whether the passage actually supports the new resolved query.
7. Include only relevant, verified passages in the current evidence bundle.

If the old source cannot be loaded or verified, do fresh retrieval.

### 7.2 Retrieval behavior by intent

**CONTINUE**

- Load relevant previous evidence by canonical IDs.
- Verify source freshness and relevance.
- Reuse it if it supports the current follow-up.
- If evidence is insufficient, perform fresh retrieval.

**EXPAND**

- Load and validate relevant previous evidence.
- Run the existing hybrid retrieval pipeline for the resolved query.
- Merge old and new evidence.
- Deduplicate by canonical document/chunk identity.
- Preserve retrieval provenance (`reused` versus newly retrieved).

**NEW_TOPIC**

- Run the existing retrieval pipeline from the new query.
- Do not include unrelated prior sources.
- Do not use previous assistant prose as factual evidence.

**CLARIFY**

- Ask one concise clarification question.
- Do not generate an unsupported substantive legal answer.
- Save the clarification turn according to the existing chat persistence convention.

### 7.3 Keep the existing RAG retrieval intact

Fresh retrieval must use the project's existing pipeline:

```text
Resolved query
    |
    +--> Existing query normalization / area handling
    |
    +--> Existing deterministic scope gate
    |
    +--> Qdrant dense retrieval
    |
    +--> BM25 lexical retrieval
    |
    +--> Existing exact-section lookup (if applicable)
    |
    +--> Existing RRF fusion
    |
    +--> Existing deduplication / diversification / source filters
    |
    +--> Existing score gate and official-source fallback
```

Do not replace this pipeline or bypass its filters.

### 7.4 Citation generation for each follow-up

- Generate citations from the evidence bundle used for the current answer.
- Rebuild citation labels for every assistant turn.
- Never copy old citation labels without rebuilding their mapping.
- Every material legal claim must cite a source in the current evidence bundle.
- If the old source is reused, it may receive a new label in the current answer.
- A new source must be added to the current turn's source mapping.
- The frontend must render the current answer's citations correctly.
- Do not imply that a source supports a claim unless the retrieved passage actually supports it.

---

## 8. Answer generation and legal safety

Extend the existing answer prompt carefully; do not replace it wholesale.

The answer-generation model receives:

- Original current citizen message.
- Resolved standalone query.
- Bounded conversation context needed to understand references.
- Current verified evidence bundle.
- Existing answer constraints and citation format.

Mandatory rules:

1. Conversation history is context, not legal evidence.
2. Previous assistant answers are not authoritative.
3. Only the current verified evidence bundle may support legal/public-service factual claims.
4. Do not invent law sections, dates, fees, deadlines, compensation amounts, complaint channels or government procedures.
5. Cite every material legal claim according to the existing citation format.
6. If the available evidence does not answer the follow-up, say so and use the existing partial/refusal/clarification policy.
7. If a previous answer appears incorrect or is contradicted by current evidence, correct it explicitly and politely.
8. Use clear, accessible Bangla by default, preserving the citizen's language preference where supported.

Keep the existing citation validator and trust/status policy in the generation flow. Do not weaken them to make follow-ups appear successful.

---

## 9. Suggested orchestration flow

Use the existing chat service and pipeline. The following is conceptual pseudocode, not a request to create duplicate placeholder functions:

```python
async def handle_chat(request, owner):
    conversation = await get_or_create_authorized_conversation(
        conversation_id=request.conversation_id,
        owner=owner,
    )

    history = await load_recent_turns(conversation.id)
    previous_sources = await load_previous_source_references(conversation.id)

    if not history:
        resolution = initial_query_resolution(request)
    else:
        resolution = await resolve_followup(
            message=request.message,
            history=history,
            previous_sources=previous_sources,
            requested_area=request.area,
        )

    if resolution.intent == "CLARIFY":
        result = build_clarification_result(resolution)
        return await persist_turn_and_return(conversation, request, result)

    # Run the existing scope/safety checks on the resolved query.
    await existing_scope_and_safety_checks(resolution.resolved_query)

    if resolution.intent == "CONTINUE":
        evidence = await load_and_validate_previous_evidence(
            previous_sources, resolution
        )
        if not evidence_is_sufficient(evidence, resolution):
            fresh = await existing_hybrid_retrieval(resolution.resolved_query)
            evidence = merge_and_deduplicate(evidence, fresh)

    elif resolution.intent == "EXPAND":
        old = await load_and_validate_previous_evidence(
            previous_sources, resolution
        )
        fresh = await existing_hybrid_retrieval(resolution.resolved_query)
        evidence = merge_and_deduplicate(old, fresh)

    else:  # NEW_TOPIC or initial query
        evidence = await existing_hybrid_retrieval(resolution.resolved_query)

    # Continue through existing score gate, official fallback,
    # grounded generation, citation validation and trust policy.
    result = await existing_answer_pipeline(
        original_question=request.message,
        resolved_query=resolution.resolved_query,
        conversation_context=history,
        evidence=evidence,
    )

    # Persist messages and exact source mappings consistently.
    return await persist_turns_sources_and_return(
        conversation=conversation,
        request=request,
        result=result,
        evidence=evidence,
    )
```

Implementation requirements:

- Use actual service/function names found in the repository.
- Keep the initial-question path working.
- Persist the citizen message and assistant result with clear failure semantics.
- Save assistant turn and source mappings in one database transaction where possible.
- Do not return a successful persisted-turn response if the database write failed.
- Handle concurrent messages in the same conversation safely (transaction/locking or equivalent).
- Do not cache context-dependent follow-up answers using a cache key that ignores conversation context. If the existing cache is not conversation-aware, bypass it for follow-ups.

---

## 10. Frontend integration

Inspect the current Next.js chat state and API client before editing.

Implement only the minimum UI behavior:

1. Store the active `conversation_id` for the current chat.
2. On the first message, accept the ID returned by the backend.
3. Send the same ID with every subsequent message in that chat.
4. Keep the existing message history visible.
5. Add or preserve a “New chat” action that clears the active conversation ID and starts a new conversation.
6. Preserve existing voice input, speech-to-text, TTS, citations, loading/error states and responsive UI.
7. Handle expired, deleted or unauthorized conversations safely; offer the user a way to start a new chat.
8. Do not redesign the UI or add unrelated chat features.

If the current frontend already maintains a session/conversation identifier, reuse it.

---

## 11. Context window and performance

- Load only the last 5–10 relevant turns initially, subject to the model's token budget.
- Keep the original current question intact.
- Keep `resolved_query` separate.
- Do not summarize away legally material facts such as dates, amounts, employment status, location or negation.
- Do not load every source from the entire conversation; load sources attached to the relevant recent assistant turn(s).
- Avoid an extra LLM call when there is no conversation history.
- Use deterministic heuristics for obvious cases where safe, but use the resolver when reference resolution is genuinely needed.
- Do not introduce Redis, LangGraph, Celery or another new infrastructure/framework for this feature.

---

## 12. Tests and acceptance criteria

Add tests using the repository's existing test framework and patterns.

### Follow-up behavior

- [ ] Initial question creates or uses a conversation.
- [ ] Follow-up with the same `conversation_id` loads the correct history.
- [ ] Missing `conversation_id` preserves the existing API behavior.
- [ ] CONTINUE reuses relevant previous evidence.
- [ ] EXPAND reuses relevant evidence and performs fresh retrieval.
- [ ] NEW_TOPIC performs fresh retrieval without unrelated old sources.
- [ ] CLARIFY asks a question instead of guessing.
- [ ] Bangla follow-up references such as “তাহলে”, “এটার জন্য”, “ওই আইন” resolve correctly.
- [ ] Banglish follow-up examples are handled where the current normalization stack supports them.

### Evidence and citations

- [ ] The system reloads source passages by canonical IDs, not from old assistant prose.
- [ ] Reused evidence is checked for existence, relevance and freshness.
- [ ] Missing/stale/repealed evidence is not blindly reused.
- [ ] New evidence is merged and deduplicated correctly.
- [ ] Citation labels are generated for the current assistant turn.
- [ ] Each citation maps to the correct document/chunk/section.
- [ ] Previous assistant answers are never treated as legal evidence.
- [ ] Insufficient evidence follows the existing refusal/partial policy.

### Security and privacy

- [ ] Conversation ownership is checked on every request.
- [ ] One user cannot access another user's conversation.
- [ ] User-provided content is treated as untrusted data, not instructions.
- [ ] Personal uploaded document contents/OCR text are not newly persisted by this feature.
- [ ] Existing personal-document privacy and retention behavior remains unchanged.

### Regression and frontend

- [ ] Existing initial chat behavior still works.
- [ ] Existing citations, voice input, transcription and TTS still work.
- [ ] Existing domain/scope gate, retrieval, official fallback and trust policy remain intact.
- [ ] Frontend sends and retains `conversation_id`.
- [ ] New chat starts a fresh conversation.
- [ ] Backend tests and frontend lint/build checks pass.

---

## 13. Non-goals — do not implement

- Redis or any new cache infrastructure.
- Replacing PostgreSQL, Qdrant or BM25.
- Rewriting the existing RAG pipeline.
- Adding a general-purpose autonomous agent or LangGraph.
- Adding unrelated user profiles, analytics, admin dashboards or chat-sharing features.
- Persisting personal uploaded document contents.
- Treating conversation summaries or old answers as legal evidence.
- Rewriting the UI design.
- Claiming legal authority or guaranteed correctness.

---

## 14. Required final report from the coding agent

After implementation, report:

1. What conversation/source-continuity functionality already existed.
2. What was added and why.
3. Exact files changed.
4. Database migration/schema changes, if any.
5. How conversation ownership is enforced.
6. How CONTINUE / EXPAND / NEW_TOPIC / CLARIFY are decided.
7. How old sources are reloaded and freshness-checked.
8. How current-turn citations map to canonical sources.
9. Confirmation that personal uploaded document contents were not persisted.
10. Exact test commands and actual pass/fail results.
11. Any known limitations or incomplete work.

**Do not claim tests passed unless they were actually executed. Do not make destructive schema changes.**

---

## Final engineering rule

**The conversation provides context. The cited source provides evidence. A follow-up answer must continue the context while verifying that its evidence still supports the new question.**

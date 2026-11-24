# AdhikarAI — Official Source Conflict Detection & Transparency

## Implementation Specification for Coding Agent

**Feature scope:** Detect, classify, and transparently communicate disagreements between official documents about the same Bangladesh public service, especially fees, processing times, and required paperwork.

**Repository:** https://github.com/jihadmia35/Adhikar-AI

---

## 1. Objective

Implement a reliable feature that prevents AdhikarAI from silently selecting one of multiple conflicting official sources and presenting that information as certain.

When retrieved official documents disagree about a service, the system must:

1. Detect whether the documents actually refer to the same service and context.
2. Extract comparable claims from the documents.
3. Identify and classify genuine disagreements.
4. Resolve a disagreement only when reliable evidence supports a resolution.
5. Otherwise disclose the disagreement, cite the relevant sources, and clearly communicate uncertainty.
6. Preserve source provenance so every displayed claim can be traced to its original document and passage.

Guiding principle:

> When official sources disagree, AdhikarAI should communicate the disagreement, not manufacture certainty.

This is a trust/evidence capability inside the existing RAG application, not a new chatbot mode.

---

## 2. Scope and Non-Goals

### In scope

- Conflicting official information about fees, processing times, required/optional documents, eligibility, applicant categories, application methods, service conditions, and validity periods.
- Metadata-aware comparison of official documents.
- Structured claim extraction and normalization.
- Context matching before comparison.
- Conflict classification.
- Evidence-based conflict resolution.
- Transparent answer generation with citations.
- Auditability and tests.

### Explicitly out of scope

Do not implement or redesign:

- Follow-up conversation/source-continuity mode.
- Redis or caching infrastructure.
- A new RAG architecture or replacement retrieval system.
- A new vector database or search provider.
- Agentic workflows, MCP, or unrelated AI features.
- A new frontend design system.
- Automatic legal interpretation beyond evidence and rules supported by the repository.

Do not rewrite existing functionality. Integrate this feature into the current pipeline with the smallest maintainable changes.

---

## 3. Mandatory Repository Audit Before Coding

First inspect the actual repository. Do not assume the architecture from this specification.

Inspect at least:

- Project structure and README.
- Existing document ingestion and parsing pipeline.
- Document/chunk database models and migrations.
- Source metadata currently stored.
- Retrieval pipeline, including dense retrieval, BM25, fusion/reranking, filters, and thresholds.
- RAG orchestration and prompt construction.
- Citation generation and citation validation.
- Official-source verification or trust rules, if present.
- Existing API response schemas.
- Frontend answer and citation rendering.
- Existing tests and test conventions.

Write a short implementation plan based on the actual code before changing files.

Reuse existing models, services, schemas, and conventions wherever possible. If a required metadata field already exists, do not duplicate it.

If the repository does not contain enough information to establish source authority or effective dates, represent those fields as unknown. Never fabricate metadata.

---

## 4. Core Design

Add a **Conflict Detection & Transparency** stage after retrieval and before final answer generation.

```text
User query
    |
Existing query processing
    |
Existing hybrid retrieval
    |
Retrieved source chunks
    |
Claim extraction and normalization
    |
Context matching
    |
Conflict detection
    |
Evidence-based resolution
    |
Answer generation with conflict context
    |
Existing citation validation
    |
API response / frontend
```

The existing retrieval pipeline remains the source of candidate evidence. Conflict detection must not bypass retrieval filters, access controls, source restrictions, or citation validation.

For the first implementation, compare relevant claims found in retrieved evidence for the current query. Do not build a repository-wide crawler or background re-indexing platform unless the existing architecture already provides one and it is necessary.

---

## 5. Source Metadata and Provenance

### 5.1 Required metadata

Audit the existing document model first. Reuse existing fields and add only missing fields.

Where available, support:

| Field | Description |
|---|---|
| `document_id` | Stable ID of the original document |
| `publisher` | Issuing authority or organization |
| `source_url` | Original official URL |
| `source_type` | Law, rule, gazette, circular, official notice, service portal, FAQ, etc. |
| `publication_date` | Date published |
| `effective_from` | Date the information becomes effective |
| `effective_until` | End of validity, if explicitly known |
| `document_status` | Active, superseded, repealed, draft, archived, unknown |
| `supersedes_document_id` | Explicitly identified previous document, if known |
| `verified_at` | Last verification date, if supported |
| `authority_level` | Existing or carefully defined source-authority classification |

All metadata must be evidence-backed. Missing values must remain `null` or `unknown`.

### 5.2 Provenance for extracted claims

Every extracted claim must retain:

- Original `document_id`.
- Original `chunk_id`, page, section, or equivalent locator.
- Exact supporting text or a safe reference to the original passage.
- Source URL and publisher when available.
- Publication/effective dates when available.
- Extraction timestamp and extraction method/model version if consistent with project conventions.

Do not use an LLM-generated summary as the citation source. Citations must resolve to the original document and supporting passage.

---

## 6. Claim Extraction

Extract claims from retrieved chunks only when relevant to the current service/query.

Use a validated structured schema (Pydantic or the repository's existing schema system). Adapt field names to existing conventions.

Suggested conceptual schema:

```python
class ExtractedClaim:
    service_id: str | None
    service_name: str
    claim_type: Literal[
        "fee",
        "processing_time",
        "required_document",
        "eligibility",
        "application_method",
        "validity_period",
        "other",
    ]
    value: dict | str | int | float | list
    applicant_type: str | None
    service_variant: str | None
    jurisdiction: str | None
    conditions: list[str]
    effective_from: date | None
    effective_until: date | None
    document_id: str
    chunk_id: str
    page_number: int | None
    supporting_quote: str
    extraction_confidence: float | None
```

The exact implementation may differ, but the output must preserve the same information.

### Extraction rules

1. Extract only claims explicitly supported by the source passage.
2. Do not infer a fee, deadline, required document, or legal status from missing information.
3. Distinguish `required`, `optional`, `conditional`, and `not_mentioned` where applicable.
4. Preserve conditions, exceptions, applicant category, and service variant.
5. Normalize values without losing the original text.
6. Reject malformed or unsupported structured output.
7. If extraction confidence is low or the passage is ambiguous, mark it for uncertainty/manual review rather than treating it as a verified claim.

### Value normalization examples

**Fees**

Represent amount and currency separately. Preserve fee category and tax, VAT, urgency, delivery, or service-type conditions.

```json
{
  "amount": 700,
  "currency": "BDT",
  "fee_category": "application_fee",
  "includes_tax": null,
  "original_text": "৭০০ টাকা"
}
```

**Processing times**

Preserve the unit and whether the period uses working or calendar days.

```json
{
  "duration": 20,
  "unit": "day",
  "day_type": "working_days",
  "original_text": "২০ কার্যদিবস"
}
```

**Required documents**

Represent each document with requirement status and conditions.

```json
{
  "items": [
    {
      "document": "National ID",
      "requirement": "required",
      "condition": null
    },
    {
      "document": "Birth certificate",
      "requirement": "conditional",
      "condition": "If applicable"
    }
  ]
}
```

Do not treat an item omitted from a document as explicitly optional or explicitly not required.

---

## 7. Context Matching Before Comparison

Never compare claims merely because they mention the same service name.

Before comparing two claims, check whether they share the relevant context:

- Same service or verified service identifier.
- Same service variant or application type.
- Same applicant category.
- Same jurisdiction or issuing authority scope.
- Same relevant conditions.
- Overlapping or comparable effective periods.

If a context dimension is unknown, do not silently assume it matches. The system may mark the pair as `POSSIBLE_CONFLICT` or `INSUFFICIENT_CONTEXT`.

Examples:

- Regular application fee vs urgent application fee: context difference, not necessarily a conflict.
- Different applicant categories: context difference.
- Different effective periods: temporal difference.
- Same applicant, service, conditions, and effective period, but different fees: direct conflict.

Retain the reason why two claims were considered comparable or not comparable.

---

## 8. Conflict Classification

Support at least these statuses:

| Status | Meaning |
|---|---|
| `NO_CONFLICT` | Comparable claims agree |
| `DIRECT_CONFLICT` | Comparable claims disagree for the same context and period |
| `TEMPORAL_DIFFERENCE` | Claims apply to different effective periods |
| `CONTEXT_DIFFERENCE` | Claims apply to different applicant/service contexts |
| `POSSIBLE_CONFLICT` | A disagreement may exist, but context or metadata is incomplete |
| `INSUFFICIENT_EVIDENCE` | Not enough reliable evidence to compare |
| `RESOLVED` | Conflict resolved using a verifiable basis |

Do not classify every missing field or omission as a conflict.

### Claim-type comparison

- **Fee:** compare normalized amount, currency, fee category, and conditions.
- **Processing time:** compare duration, unit, working/calendar-day semantics, and conditions.
- **Required documents:** compare explicit requirement statuses. A document listed by one source but not mentioned by another is not automatically a contradiction.
- **Eligibility:** compare explicit criteria and conditions, not just keyword overlap.
- **Application method:** distinguish additional channels from mutually exclusive instructions.

Use deterministic comparisons for normalized values. Use an LLM only where semantic interpretation is genuinely needed, such as matching differently worded service names or interpreting conditions.

The LLM must return structured output validated by the application. It must not independently decide that one source is legally authoritative.

---

## 9. Evidence-Based Conflict Resolution

A conflict may be resolved only when repository evidence supports a defensible reason.

### Resolution signals

Evaluate, when available:

1. **Legal/source authority:** law, regulation, gazette, formal circular, official notice, service portal, FAQ, etc.
2. **Effective date:** when the instruction actually becomes applicable.
3. **Explicit supersession:** whether a later document explicitly replaces, amends, or repeals an earlier one.
4. **Current status:** active, repealed, draft, archived, or unknown.
5. **Applicability:** whether the source applies to the same service, applicant, jurisdiction, and conditions.
6. **Authenticity:** whether the document comes from a verified official source under existing trust policy.

### Critical rules

- A newer publication date alone does not prove a document supersedes an older one.
- An official FAQ must not automatically override a law, regulation, gazette, or formal circular.
- A source's authority must not be invented from its domain name alone.
- Do not assume a document is active merely because it is accessible.
- Do not infer repeal or supersession unless explicit evidence or a reliable existing source-status record supports it.
- Do not resolve a conflict by choosing whichever retrieved chunk has the highest similarity score.
- Do not let an LLM make an unsupported legal hierarchy decision.

### Resolution outcomes

Use explicit outcomes such as:

- `RESOLVED_BY_EXPLICIT_SUPERSESSION`
- `RESOLVED_BY_EFFECTIVE_DATE`
- `RESOLVED_BY_APPLICABILITY`
- `UNRESOLVED_OFFICIAL_DISAGREEMENT`
- `UNRESOLVED_INSUFFICIENT_METADATA`

Store a concise machine-readable reason and evidence supporting the decision.

If no defensible resolution exists, preserve the conflict as unresolved and disclose it to the user.

---

## 10. Answer Generation Behavior

Pass conflict analysis to the existing answer generator as structured evidence. Do not ask the model to rediscover conflicts from a long unstructured prompt.

### When no conflict exists

Generate the normal answer using existing answer and citation behavior.

### When a conflict is resolved

- State the applicable value.
- Briefly explain why one source is considered current/applicable.
- Cite the controlling source.
- Where useful, mention the superseded or inapplicable source and why it does not control the current answer.
- Do not hide a material source disagreement.

### When a conflict is unresolved

The answer must:

1. Explicitly say that official sources disagree.
2. Show the competing values or requirements.
3. Identify each source and publication/effective date when known.
4. Explain what could not be verified.
5. Avoid presenting either value as definitively current.
6. Give a safe next step, such as checking with the responsible service office or official authority.
7. Cite both original sources.

### Example response shape

```text
এই service-এর fee নিয়ে পাওয়া official document-গুলোতে ভিন্ন তথ্য রয়েছে।

- Ministry circular (published: 2024): ৳500
- Official service portal (published: 2025): ৳700

দ্বিতীয় document-টি প্রথম document-কে আনুষ্ঠানিকভাবে supersede করেছে কি না, তা যাচাই করা যায়নি। তাই বর্তমানে কোন fee প্রযোজ্য, তা নিশ্চিতভাবে বলা যাচ্ছে না।

আবেদন করার আগে সংশ্লিষ্ট service office বা responsible authority থেকে বর্তমান fee নিশ্চিত করুন।

Sources:
[Source A, page/section]
[Source B, page/section]
```

This is an example only. Use natural Bangla matching the user's query and existing response style.

### Prohibited answer behavior

- Never silently choose one conflicting value.
- Never average two fees or timelines.
- Never invent a compromise value.
- Never describe a source as latest/current/valid unless metadata supports that claim.
- Never call a document superseded without evidence.
- Never cite only one side of an unresolved conflict.
- Never turn absence of information into a negative claim.
- Never claim an authority confirmed something when retrieved evidence does not show it.

---

## 11. API and Frontend Integration

Audit the current response schema and UI before making changes.

Keep existing API behavior backward-compatible where possible.

If useful, expose an optional structured conflict object, for example:

```json
{
  "conflict_analysis": {
    "status": "UNRESOLVED_OFFICIAL_DISAGREEMENT",
    "claim_type": "fee",
    "resolution_status": "unresolved",
    "reason": "No verified supersession relationship was found.",
    "claims": [
      {
        "value": "BDT 500",
        "source_id": "document_a",
        "citation_id": "citation_a",
        "publication_date": "2024-01-10"
      },
      {
        "value": "BDT 700",
        "source_id": "document_b",
        "citation_id": "citation_b",
        "publication_date": "2025-02-10"
      }
    ]
  }
}
```

This is a conceptual schema, not a requirement to use these exact names.

Frontend requirements:

- Render a clear, accessible warning when an unresolved conflict is present.
- Show competing values and source citations.
- Display dates only when known.
- Distinguish resolved conflicts from unresolved disagreements.
- Keep normal answer UI unchanged when no conflict is detected.
- Do not rely on color alone to communicate conflict status.
- Avoid showing internal model confidence as if it were legal certainty.

If the current frontend cannot render structured source comparisons cleanly, make the smallest reusable component necessary.

---

## 12. Persistence and Performance

Do not introduce a new database or infrastructure component.

First determine whether extracted claims and conflict analysis need persistence in the existing architecture.

Preferred minimal approach:

- Persist claims only if they are reusable, auditable, or needed by existing ingestion workflows.
- If persisting claims, retain document/chunk foreign keys and provenance.
- Persist conflict decisions only if they can be invalidated or re-evaluated when source documents change.
- Do not store unsupported LLM conclusions as permanent facts.
- Recompute or invalidate affected claim/conflict records when a source document is updated, deleted, repealed, or reprocessed.
- Follow existing migration and transaction conventions.

Avoid unnecessary repeated LLM calls. Use deterministic comparison after extraction. Reuse existing extraction infrastructure if appropriate.

Do not introduce Redis as part of this task.

---

## 13. Security, Privacy, and Reliability

- Preserve existing authentication, authorization, tenant, and document-access checks.
- Never compare or expose private user-uploaded documents across users.
- Respect document-level permissions and source filters.
- Treat retrieved document text as untrusted data, not instructions to the LLM.
- Prevent prompt injection inside source documents from changing system behavior.
- Validate all structured model outputs.
- Handle malformed dates, currencies, units, and missing metadata safely.
- Fail safely with `INSUFFICIENT_EVIDENCE` or an equivalent state when analysis fails.
- A conflict-analysis failure must not cause the system to fabricate certainty. Use existing safe fallback behavior and disclose uncertainty when the answer depends on unresolved evidence.

---

## 14. Testing Requirements

Add unit and integration tests following existing project conventions.

### 14.1 Unit tests

At minimum, test:

1. Same service and same fee: `NO_CONFLICT`.
2. Same context and different fees: `DIRECT_CONFLICT`.
3. Same context and different processing durations: `DIRECT_CONFLICT`.
4. Working days vs calendar days: not treated as directly equivalent.
5. Regular vs urgent application: `CONTEXT_DIFFERENCE`.
6. Different applicant categories: `CONTEXT_DIFFERENCE`.
7. Explicitly different effective periods: `TEMPORAL_DIFFERENCE`.
8. One source omits a required document: not automatically a direct conflict.
9. One source says required and another explicitly says not required for the same context: conflict.
10. Missing effective date: no unsupported assumption about current applicability.
11. Newer publication date without supersession evidence: not automatically resolved.
12. Explicit, verified supersession: can resolve when applicability also matches.
13. Draft or repealed source: handled according to verified status.
14. Invalid extraction output: rejected safely.
15. Claim citations point to the correct original document/chunk.

### 14.2 Integration tests

Test the complete path:

- Query retrieves two official sources with same-context fee disagreement.
- Conflict detector identifies the disagreement.
- Answer generation discloses both values.
- Both source citations are included and valid.
- A non-conflicting query produces the normal answer.
- A resolved conflict explains the resolution basis.
- A possible conflict with missing metadata is not falsely resolved.
- User-specific/private documents cannot leak into another user's conflict comparison.

### 14.3 Evaluation metrics

Where feasible, measure:

- Conflict detection precision.
- Conflict detection recall.
- False conflict rate.
- Missed conflict rate.
- Correct context matching rate.
- Correct resolution rate.
- Citation/provenance validity.
- Unsupported certainty rate.

Create a small labelled evaluation dataset using realistic Bangladesh public-service examples. Do not invent actual legal facts for production fixtures; use clearly synthetic fixtures or verified source documents.

---

## 15. Suggested Implementation Order

1. Audit the repository and write a short implementation plan.
2. Identify existing document metadata and citation/provenance models.
3. Add only missing source metadata support.
4. Define and validate the extracted-claim schema.
5. Implement value normalization.
6. Implement context matching.
7. Implement deterministic conflict comparison.
8. Implement evidence-based resolution rules.
9. Integrate conflict context into answer generation.
10. Add optional API response fields and minimal UI rendering.
11. Add tests and run the relevant existing test suite.
12. Document limitations and metadata the current ingestion pipeline cannot provide.

Implement incrementally. Keep each change focused and reviewable.

---

## 16. Acceptance Criteria

The feature is complete only when:

- [ ] Existing RAG retrieval continues to work without regression.
- [ ] Relevant claims can be extracted with original-source provenance.
- [ ] Fee, processing-time, and required-document claims are normalized safely.
- [ ] Claims are compared only after service/context matching.
- [ ] Genuine same-context disagreements are detected.
- [ ] Missing information is not misclassified as contradiction.
- [ ] A newer document is not automatically treated as controlling.
- [ ] Conflicts are resolved only with verifiable evidence.
- [ ] Unresolved official disagreements are explicitly disclosed.
- [ ] Both sides of an unresolved disagreement are cited.
- [ ] Resolved conflicts include the reason and controlling evidence.
- [ ] Frontend displays conflict status without disrupting normal answers.
- [ ] Access control and document privacy remain intact.
- [ ] Unit and integration tests pass.
- [ ] Existing functionality has not been unnecessarily rewritten.

---

## 17. Required Final Report from the Coding Agent

After implementation, report:

1. What the repository's actual architecture was.
2. Which files were changed and why.
3. How claims are extracted and normalized.
4. How context matching and conflict classification work.
5. Which evidence can resolve a conflict and which cases remain unresolved.
6. API/frontend changes.
7. Database migrations, if any.
8. Tests added and exact test commands/results.
9. Known limitations, especially missing source metadata.
10. A short example showing final behavior for an unresolved official-source disagreement.

Do not claim a test passed unless it was actually run. Do not claim source authority or legal correctness beyond what the implementation verifies.

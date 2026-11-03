# Architecture

ApplyAtlas has one local owner and several client profiles. It is deliberately a single-writer operator workspace, not a multi-tenant service.

## Components and boundaries

| Component | Responsibility | Authority |
|---|---|---|
| Dashboard | View roles, client facts, packets, mandates and receipts | Calls owner-token API |
| Discovery adapters | Normalise public board responses into typed jobs | Read-only source access |
| Evidence matcher | Decompose fit into reproducible scores | No side effects |
| Planner | Select existing evidence IDs and application strategy | No browser, filesystem or submission tools |
| Composer | Render career claims using exact client facts | Cannot invent career claims |
| Critic | Check IDs and factual identity; request one repair | Can block advancement |
| Policy gate | Apply score, warnings and mandate scope | Can route to review or automatic execution |
| LangGraph | Persist workflow and pause/resume client review | Stores encrypted checkpoint values |
| Submission ledger | Atomically reserve attempt and daily quota | One intent per client/job |
| Browser executor | Observe, map, fill, verify and submit known forms | Known hosted ATS forms; no arbitrary model code |

The graph state keeps application IDs, fit summaries, routing decisions and approved packet hashes. Profiles, document packets and receipts live in the application store. Every checkpoint value and intermediate write is encrypted by a Fernet serializer around LangGraph's serializer.

## Reasoning and repair

The optional planner sees the job and the client's evidence statements. It chooses up to eight existing evidence IDs and one of three strategies. JSON output is parsed with a strict Pydantic schema. Unknown IDs fail the critic. The repair route runs once and uses known facts; a second critic failure blocks the packet. Provider errors use an explicitly labelled deterministic fallback.

This constrains model authority: a hostile job description may influence relevance ranking, but it cannot install tools, fetch secrets, invent an evidence ID that passes checking or authorise a submission. The instruction-pattern detector is a review heuristic, not a comprehensive prompt-injection classifier.

## Submission transaction

1. Generate the packet and hash its complete content.
2. Hash the candidate, job content and policy snapshot separately.
3. Obtain a matching per-packet approval or a currently valid automatic mandate.
4. Re-check both hashes and the mandate.
5. In `BEGIN IMMEDIATE`, check the daily limit and insert the unique submission attempt.
6. Invoke the browser once.
7. Record an explicit employer acknowledgement or an uncertain outcome.

SQLite and the remote employer cannot participate in a single transaction. Therefore the system provides at-most-one automated attempt per application record, not an exactly-once remote application guarantee. A crash between Submit and local acknowledgement must be reconciled manually. That tradeoff favours avoiding a second application over automatic recovery of an ambiguous side effect.

## Identity and duplicate detection

Jobs are grouped using a fingerprint of normalised company, title and location. This catches common board mirrors and the client/job uniqueness constraint catches repeated runs. It can merge distinct requisitions sharing all three values or miss an employer with different names on different boards. Requisition-aware entity resolution is a future extension. Discovery timestamps do not invalidate an existing approval, while content changes do.

## Storage and event integrity

- `atlas.db`: encrypted profiles, packets and receipts; public job data; operational events, attempts and outcomes.
- `checkpoints.db`: encrypted LangGraph checkpoint values and writes. Checkpoint indexing metadata can expose application identifiers and node names.
- `vault.key`: local encryption key, owner-only permissions at creation.
- `owner-token.txt`: generated local API token, owner-only permissions at creation.

Events contain operational metadata and form a SHA-256 chain. Verification detects retained-record edits without recomputing the chain. There is no external anchor or digital signature: a writer controlling the database can reconstruct the chain or remove its tail. Encryption similarly does not protect against an attacker who obtains both database and key. Use filesystem access control and encrypted device storage.

## Extension points

Add a discovery adapter returning validated `Job` objects; add a hosted form adapter with explicit required-field rules and fixture tests; add another compatible planner endpoint; or replace SQLite with a transactional service for a deployment with several operators. Keep submission authorisation outside model output.

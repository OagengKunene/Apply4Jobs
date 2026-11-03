# Operating the workspace

## A client application lifecycle

1. A client supplies verified contact information and evidence facts. The local owner creates a separate profile for that client.
2. The owner discovers company-board jobs or manually imports a posting.
3. The graph creates a fit explanation and factual document packet.
4. The client reviews each packet or supplies a scoped automatic mandate through the operator.
5. The browser submits a supported form when authorised and technically feasible.
6. The operator reads the receipt, reconciles interruptions and records outcomes.

The owner can see all clients. There are no separate client logins or isolated tenant permissions. Obtain each client's authorisation before entering their facts or enabling a model provider or live application submission. A profile is the factual source of truth; the software cannot verify that a client statement is true.

## Current working scope

- Python, the API, LangGraph workflow, local UI, PDF output and SQLite stores run locally.
- The fictional employer is the validated end-to-end submission target.
- Greenhouse and Lever connector parsers have fixture tests. Live employer GET requests may be blocked in restricted environments.
- Hosted form templates vary. The generic label mapper supports straightforward fields; required custom choices or consents stop the run. It does not solve CAPTCHAs or manage account logins.
- Review decisions persist across restarts. Packets rejected, skipped or flagged as uncertain are not automatically restarted.
- Queued FastAPI tasks run inside the API process. They are not a distributed queue. Closing the server can leave queued or running work; rerunning the same role resumes eligible graph work, while already-reserved external attempts need reconciliation.
- Use one agent writer at a time per data directory. Do not concurrently run a campaign and the API.
- A submitted result means an explicit page acknowledgement was observed; it does not establish that a recruiter read or accepted the application. The demo is always labelled separately.

## Browser and data boundaries

Initial live application URLs must use known hosted ATS domains. Top-level navigation and form action destinations are checked, unsafe schemes are rejected, and requests resolving to private networks are blocked. Side-effect requests are restricted to supported ATS hosts. DNS resolution checks are defence in depth, not a replacement for network isolation in an internet-hosted deployment.

The browser uses a new context for each application and closes it afterwards. No browser credentials or persistent login cookies are collected. Resume files are passed to Playwright as in-memory buffers. Browser screenshots are not captured during real client submissions in this version. Operational logs avoid contact fields and cover-letter payloads.

The owner token protects every `/api/` route; browser-origin checks block cross-origin API calls. The CLI serves loopback only. Keep the token private and use device encryption. There is no public sign-up flow, authentication gateway or rate limiter for public hosting. Do not expose this server to the internet without a separate deployment design.

## Backups and deletion

Stop the API and campaign before copying the data directory. Preserve both SQLite databases, their remaining WAL files if any, the encryption key and the token. Store backups on encrypted media. Losing the key makes encrypted records unreadable. Deleting client data and associated checkpoint/history records requires a deliberate administrative workflow; this version has no client-delete endpoint and makes no automatic retention promise.

## Expected interruptions

| Condition | Result / operator action |
|---|---|
| No LLM configuration | Labelled deterministic evidence selection |
| Invalid provider output | Deterministic fallback or one critic repair |
| Skill or experience gaps | Visible in packet; automatic mandate cannot silently bypass warnings |
| Below minimum score | Application skipped |
| Out-of-scope employer, expired mandate | Packet awaits client review |
| Changed facts, job or policy after review | Stale submission approval blocked |
| Required unanswered form choice or consent | Needs attention; client completes the portal manually |
| Live submission setting disabled | Needs attention; no employer browser submission |
| Daily budget exhausted | Needs attention; reservation cannot exceed the limit |
| Browser failure or no acknowledgement | Needs attention; inspect employer portal before any deliberate reset |

## Roadmap, not implemented

Resume PDF extraction with client fact verification; richer per-ATS adapters; client-separated sign-in; a distributed queue and PostgreSQL; requisition-aware deduplication; externally anchored audit records; approval regeneration after edits; inbox status sync; and production deployment hardening. These are not claimed as working features of v0.1.

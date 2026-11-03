# Security reporting and scope

This is a local development and controlled-pilot application. Do not expose the owner API on the public internet. Do not commit `.env`, client data, encryption keys, browser sessions or owner tokens.

Report a suspected security issue privately to the repository owner through GitHub's available private reporting mechanism. If private reporting is unavailable, create an issue requesting a private contact channel without including client records, credentials or exploit details.

The model cannot authorise a submission or run arbitrary browser commands. Public job text is untrusted input. Exact evidence selection and schema validation limit what it can change; the prompt-injection warning is heuristic. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for encryption, event-chain and external-side-effect limitations.

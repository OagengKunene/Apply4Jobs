# Validation record

Validation date: 3 November 2026. Environment: Python 3.12, Linux.

## Local checks

The non-browser tests exercise the workflow, API, source response parsing, matching, evidence repair, resumable review, stale approvals, duplicate attempts, encryption, concurrent quotas and audit tampering. Browser integration tests are included and require Chromium.

At the first local full-suite run, 37 tests passed and 5 Chromium-dependent tests were blocked by the execution environment: Chromium terminated at startup because a required socket operation was denied. The browser download path also returned an incomplete archive. These are recorded as test-environment blockers, not passing browser checks.

JavaScript syntax checking and Ruff passed. The optional live LLM call, optional JobSpy dependency, Docker build and real employer submissions were not exercised locally. Greenhouse and Lever parsing was checked against fixture responses. No real applicant data was used and no employer application was submitted.

## Continuous integration

The repository workflow installs managed Chromium and runs the full suite, including the actual hosted local form and dashboard interaction tests. Its run result is authoritative for that execution environment. Screenshot capture is enabled in CI and uploaded with the test results for inspection; until a run succeeds, browser functionality should not be described as verified.

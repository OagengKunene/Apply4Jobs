# Validation record

Validation date: 3 November 2026. Environment: Python 3.12, Linux.

## Verified result

**42 tests passed in 14.76 seconds** in [GitHub Actions run 41702022893](https://github.com/OagengKunene/Githubtest/actions/runs/41702022893), testing source commit `0f808beaacee6392bf9c69f160480330ae6909a5`. Dependency installation, managed Chromium installation and Ruff also succeeded.

The passing browser checks include an actual form fill and submission, stopping on unknown required fields and required consent, the complete dashboard prepare/review/submit flow, a sandbox receipt, absence of uncaught JavaScript errors during that flow, and a mobile horizontal-overflow check. All browser submissions targeted fictional loopback-only employers, not real companies.

Desktop and mobile screenshots are committed as [workspace.png](workspace.png) and [mobile.png](mobile.png). The original CI artifact contained JUnit XML and both screenshots. Its SHA-256 was verified after download: `1c4e35438c287162b6c53595d259b7916db2cf8f7278e181b21b341d357a9126`.

## Local checks

The non-browser tests exercise the workflow, API, source response parsing, matching, evidence repair, resumable review, stale approvals, duplicate attempts, encryption, concurrent quotas and audit tampering. Browser integration tests are included and require Chromium.

Locally, 37 non-browser tests passed. Five Chromium-dependent tests were blocked by the execution environment: Chromium terminated at startup because a required socket operation was denied. The browser download path also returned an incomplete archive. GitHub's clean runner subsequently ran all 42 tests successfully, resolving the browser-verification gap for that environment.

JavaScript syntax checking and Ruff passed. A distributable wheel built successfully and contains all three dashboard assets. The optional live LLM call, optional JobSpy dependency, Docker build and real employer submissions were not exercised. Greenhouse and Lever parsing was checked against fixture responses. No real applicant data was used and no employer application was submitted.

## Continuous integration

The repository workflow installs managed Chromium and runs the full suite, including the actual hosted local form and dashboard interaction tests. Its run result is authoritative for that execution environment. Screenshot capture is enabled in CI and uploaded with the test results for inspection. Live ATS form compatibility varies; passing a sandbox test does not establish compatibility with every employer's custom form.

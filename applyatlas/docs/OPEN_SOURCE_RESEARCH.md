# Open-source research and design decisions

Primary project pages and official API documentation were reviewed on 3 November 2026. Features below describe upstream documentation, not performance independently measured by ApplyAtlas.

| Source | Useful idea | What ApplyAtlas incorporates |
|---|---|---|
| [JobSpy](https://github.com/speedyapply/JobSpy) · [MIT licence](https://github.com/speedyapply/JobSpy/blob/main/LICENSE) | One normalised discovery interface for several boards | Optional normal dependency and a typed adapter for Indeed/South Africa; default discovery uses official ATS GET APIs |
| [fahadNoufal/job-application-agent](https://github.com/fahadNoufal/job-application-agent) | Recoverable graph workflow, review mode, separate platform adapters | Independently written LangGraph nodes, encrypted checkpoints, interrupted review and hosted ATS adapters |
| [janga-raj/job-application-agent](https://github.com/janga-raj/job-application-agent) | Match, tailor and fill as separate stages | Separate matching, evidence selection, composition, critique, policy and execution stages |
| [browser-use](https://github.com/browser-use/browser-use) · [MIT licence](https://github.com/browser-use/browser-use/blob/main/LICENSE) | A browser observation/action/verification loop | A constrained Playwright executor; browser-use is not a runtime dependency and its code is not copied |
| [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | Durable human decisions with `interrupt()` and `Command` | Actual interrupted packet review, resumed by matching document hash |
| [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) | Public GET jobs, separate authenticated application POST | Company-board discovery; applicant-hosted form submission rather than pretending employer credentials are available |
| [Lever postings API](https://github.com/lever/postings-api) | Published job normalisation and hosted `applyUrl` | Discovery from public postings and application navigation to the hosted form |

No upstream application source files, interface assets, prompts or resume templates were copied. The dependency integrations are real; the conceptual inspirations are explicitly distinguished from code reuse. Original ApplyAtlas additions include exact evidence lineage, a profile/job/policy snapshot bound to approval, an atomic uncertain-outcome submission ledger, a fictional test employer and source-outcome statistics.

Some repositories using the AIHawk name had different or changed licences and project purposes in the reviewed material. ApplyAtlas does not vendor their code or base its licence on a fork's description. Upstream licences must be checked again before any future code is copied.

# Bank Assistant — assessment presentation

## Scope and current evidence

This submission addresses both the grounding assessment and Challenge B: an agent proposes a simulated transfer, while a separately authenticated reviewer decides whether to execute it. No bank or payment provider is connected.

The implementation and AIFindr OAuth flow have been exercised. Part 1 has a completed 20-case baseline and candidate comparison, but the first candidate regressed. A revised candidate has been saved; it must not be described as an improvement until its evaluation is verified. The native AIFindr review-request form exists, but rendering and submission in Playground remain to be verified.

## Part 1 — hypothesis, experiment and findings

The hypothesis was that explicit evidence requirements would reduce unsupported product claims and inappropriate account-specific assertions. The fixed dataset contains 20 English questions and success criteria. Control ran before Variant B, with the same Agent workflow, model, knowledge version and judge configuration.

Control passed 19/20 cases (95%); Variant B passed 17/20 (85%). One case improved and three regressed. The [evaluation report](../evaluations/results/2026-09-08-grounding.md) contains per-run links, measurements and three before/after examples:

- Account comparison improved its source selection and separation of product types.
- Preapproval handling regressed by implying that unavailable account metadata had been checked.
- Mortgage documentation regressed to an empty response despite successful retrieval.

Manual review also found disagreement with the judge on an identity-verification refusal. The original score is retained. One run per prompt is insufficient to establish statistical significance; lower displayed token totals are not a complete cost estimate.

The revised candidate distinguishes missing metadata from a verified empty result, requires a substantive answer after retrieval, and follows the platform's configured output schema. Raw project prompts and transcripts remain private. The delivered dataset, scripts and result records support reproduction without publishing confidential project content.

## Part 2 — demonstrated flow

The AIFindr DEV agent connected to the public HTTPS MCP through OAuth and created a synthetic EUR 25 proposal. A Playwright test opened that proposal's exact review link, signed in, checked the explicit confirmation box and submitted confirmation. The agent then queried the action and returned `executed` with `simulated: true`. The audit recorded proposal, reviewer confirmation and simulated execution. Browser automation acted as the review user for this test.

To reproduce, follow the [README](../README.md): start both services, connect the MCP, request a transfer to a `DEMO-*` destination, open its `review_url`, and explicitly confirm or reject it. The model has only proposal and status tools.

The native AIFindr component records a review request; its lead-form submission cannot authorize a transfer. Acceptance uses the reusable Next.js `TransferReview` component and an authenticated Server Action. The gateway supplies the review link from its own configuration.

## Architecture and validation

FastAPI and MCP share a deterministic policy and SQLite action/audit storage. Next.js keeps the separate reviewer credential on the server. Integer cents, immutable proposal fingerprints, fixed server-side ownership and idempotency checks constrain model-generated input. SQLite transactions serialize confirmation and simulated execution.

Backend checks cover replay, conflicting retries, altered proposals, expiration, owner isolation and OAuth token rotation. Frontend checks include lint, production build, type checking and the review E2E, including mobile overflow. The [local benchmark](../evaluations/results/gateway-benchmark.json) measured 100 actions: median 16.117 ms, P95 17.067 ms. Thirty-two concurrent confirmation retries produced one execution event. These timings exclude HTTP and LLM work.

## Trade-offs and remaining limits

The assessment uses one shared reviewer, a single SQLite instance and synchronous simulation. A temporary tunnel must remain running; its address is not a permanent deployment. Real payments would require stronger identity, durable external audit, provider idempotency and reconciliation. This implementation makes no exactly-once claim for an external service.

The first prompt candidate should not replace Control on the available evidence. Verification of the revised candidate and native Playground form is still outstanding; the repository must not be represented as a fully completed assessment until these checks are closed.

## AI assistance

Codex assisted with requirement analysis, implementation, documentation, official documentation research and test execution. No subagents were used. The candidate requested the stack and integration direction; implementation choices were developed with AI assistance and require the candidate's review and ownership. No delivery email was sent. Credentials, raw prompts, transcripts and local runtime state are excluded from Git.
